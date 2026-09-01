from __future__ import annotations

import hashlib
import unittest

from opencntx.security import (
    CONFIDENCE_HIGH,
    CONFIDENCE_WARNING,
    assess_findings,
    finding_record,
    format_finding,
    scan_text,
)


def scan(value: str, *, path: str = "sample.txt"):
    return scan_text(
        path=path,
        text=value,
        source_sha256=hashlib.sha256(value.encode("utf-8")).hexdigest(),
    )


class SecretPolicyTests(unittest.TestCase):
    def test_high_confidence_synthetic_corpus_blocks(self) -> None:
        corpus = {
            "private-key-header": "-----BEGIN " + "PRIVATE KEY-----\nsynthetic\n",
            "github-classic-token": "gh" + "p_" + ("A" * 36),
            "github-fine-grained-token": "github_" + "pat_" + ("B" * 50),
            "aws-secret-access-key": "AWS_SECRET_ACCESS_KEY=" + ("C" * 40),
            "provider-credential-stripe": "sk_" + "live_" + ("D" * 24),
            "provider-credential-openai": "sk-" + "proj-" + ("E" * 24),
            "provider-credential-slack": "xo" + "xb-" + ("F" * 16),
            "provider-credential-aws-id": "AK" + "IA" + ("G" * 16),
        }
        for expected_rule, value in corpus.items():
            with self.subTest(rule=expected_rule):
                findings = scan(value)
                self.assertEqual(len(findings), 1)
                self.assertEqual(
                    findings[0].rule_id,
                    "provider-credential"
                    if expected_rule.startswith("provider-credential-")
                    else expected_rule,
                )
                self.assertEqual(findings[0].confidence, CONFIDENCE_HIGH)
                assessment = assess_findings(findings, ())
                self.assertEqual(assessment.blocked, findings)
                self.assertEqual(assessment.warnings, ())

    def test_lower_confidence_synthetic_corpus_warns_without_blocking(self) -> None:
        corpus = {
            "credential-like-assignment": "client_secret=synthetic-value",
            "basic-auth-url": "https://demo-user:demo-pass@example.invalid/path",
            "bearer-credential": "Authorization header: Bearer abcdefghijklmnop",
        }
        for expected_rule, value in corpus.items():
            with self.subTest(rule=expected_rule):
                findings = scan(value)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].rule_id, expected_rule)
                self.assertEqual(findings[0].confidence, CONFIDENCE_WARNING)
                assessment = assess_findings(findings, ())
                self.assertEqual(assessment.warnings, findings)
                self.assertEqual(assessment.blocked, ())

    def test_structured_password_signals_are_detected(self) -> None:
        corpus = {
            "json-password": '{"password": "correct-horse-battery-staple"}\n',
            "postgres-credential-url": (
                "DATABASE_URL=postgres://app:correct-horse-battery-staple@"
                "db.example.invalid:5432/app\n"
            ),
            "db-password": "DB_PASSWORD=correct-horse-battery-staple\n",
            "database-password": "DATABASE_PASSWORD=correct-horse-battery-staple\n",
            "app-secret": "APP_SECRET=correct-horse-battery-staple\n",
            "quoted-password-with-spaces": (
                '{"password": "correct horse battery staple"}\n'
            ),
        }
        for name, value in corpus.items():
            with self.subTest(name=name):
                findings = scan(value, path="config.json")
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].confidence, CONFIDENCE_WARNING)
        self.assertEqual(scan(corpus["json-password"])[0].rule_id, "credential-like-assignment")
        self.assertEqual(scan(corpus["postgres-credential-url"])[0].rule_id, "basic-auth-url")
        self.assertEqual(scan(corpus["db-password"])[0].rule_id, "credential-like-assignment")

    def test_additional_credential_url_schemes_are_detected(self) -> None:
        corpus = (
            "mysql://app:synthetic-password@db.example.invalid/app",
            "mysql+pymysql://app:synthetic-password@db.example.invalid/app",
            "mariadb://app:synthetic-password@db.example.invalid/app",
            "mongodb://app:synthetic-password@db.example.invalid/app",
            "mongodb+srv://app:synthetic-password@cluster.example.invalid/app",
            "redis://app:synthetic-password@cache.example.invalid/0",
            "rediss://app:synthetic-password@cache.example.invalid/0",
            "amqp://app:synthetic-password@queue.example.invalid/vhost",
            "ftp://app:synthetic-password@files.example.invalid/path",
        )
        for value in corpus:
            with self.subTest(value=value.split(":", 1)[0]):
                findings = scan(value)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].rule_id, "basic-auth-url")
                self.assertEqual(findings[0].confidence, CONFIDENCE_WARNING)

    def test_prefixed_credential_assignments_are_detected_by_category(self) -> None:
        corpus = (
            "MY_API_KEY=syntheticValue123",
            "APP_TOKEN=syntheticValue123",
            "secret=syntheticValue123",
            "private_key: syntheticValue123",
            "passphrase=syntheticValue123",
            "service_auth_token=syntheticValue123",
        )
        for value in corpus:
            with self.subTest(key=value.split("=", 1)[0].split(":", 1)[0]):
                findings = scan(value)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].rule_id, "credential-like-assignment")
                self.assertEqual(findings[0].confidence, CONFIDENCE_WARNING)

    def test_normal_code_and_secret_documentation_are_bounded(self) -> None:
        quiet_corpus = (
            "token_count = len(parts)\n",
            "password = prompt_user()\n",
            "private_key = load_key()\n",
            "APP_TOKEN = fetch_token()\n",
            "The word secret alone is not a credential.\n",
            "The password field is required.\n",
            'password = ""\n',
            "token = None\n",
            '{"api_key": "example"}\n',
            "authorization: omitted\n",
            "DATABASE_PASSWORD = read_secret()\n",
            "APP_SECRET = load_from_vault()\n",
            "mongodb://cluster.example.invalid/app\n",
            "redis://cache.example.invalid/0\n",
            "amqp://queue.example.invalid/vhost\n",
            "ftp://files.example.invalid/path\n",
            "sk_live_example\n",
            "sk-proj-example\n",
            "xoxb-example\n",
            "AKIAEXAMPLE\n",
        )
        for value in quiet_corpus:
            with self.subTest(value=value):
                self.assertEqual(scan(value), ())

        documentation = (
            "Use client_secret=replace-this-value in documentation, never a real value.\n"
        )
        findings = scan(documentation, path="docs/secrets.md")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].confidence, CONFIDENCE_WARNING)

    def test_high_confidence_overlap_suppresses_lower_warning(self) -> None:
        value = "token=gh" + "p_" + ("D" * 36)
        findings = scan(value)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "github-classic-token")
        self.assertEqual(findings[0].confidence, CONFIDENCE_HIGH)

    def test_findings_are_safe_sorted_and_deterministic(self) -> None:
        first_value = "token=warning-value\n"
        second_value = "-----BEGIN " + "PRIVATE KEY-----\n"
        text = first_value + second_value
        findings = scan(text, path="folder/example.txt")
        repeated = scan(text, path="folder/example.txt")

        self.assertEqual(findings, repeated)
        self.assertEqual([finding.line for finding in findings], [1, 2])
        rendered = "\n".join(format_finding(finding) for finding in findings)
        records = repr([finding_record(finding, disposition="test") for finding in findings])
        self.assertNotIn("warning-value", rendered)
        self.assertNotIn("warning-value", records)
        self.assertNotIn("PRIVATE KEY", rendered)
        self.assertNotIn("PRIVATE KEY", records)

    def test_line_endings_keep_logical_location_but_change_byte_binding(self) -> None:
        secret = "gh" + "p_" + ("E" * 36)
        lf = scan("before\n" + secret + "\n")
        crlf = scan("before\r\n" + secret + "\r\n")
        self.assertEqual((lf[0].rule_id, lf[0].line), (crlf[0].rule_id, crlf[0].line))
        self.assertNotEqual(lf[0].finding_id, crlf[0].finding_id)

    def test_source_or_path_drift_changes_finding_id(self) -> None:
        secret = "gh" + "p_" + ("F" * 36)
        original = scan(secret, path="source.txt")[0]
        source_drift = scan(secret + "\n", path="source.txt")[0]
        path_drift = scan(secret, path="folder/source.txt")[0]
        self.assertNotEqual(original.finding_id, source_drift.finding_id)
        self.assertNotEqual(original.finding_id, path_drift.finding_id)

    def test_override_must_be_exact_current_high_and_unique(self) -> None:
        high = scan("-----BEGIN " + "PRIVATE KEY-----\n")[0]
        warning = scan("password=synthetic-value\n")[0]

        assessment = assess_findings((high, warning), (high.finding_id,))
        self.assertEqual(assessment.overrides, (high,))
        self.assertEqual(assessment.blocked, ())
        self.assertEqual(assessment.warnings, (warning,))

        with self.assertRaisesRegex(ValueError, "only once"):
            assess_findings((high,), (high.finding_id, high.finding_id))
        with self.assertRaisesRegex(ValueError, "64 lowercase hexadecimal"):
            assess_findings((high,), ("not-an-id",))
        with self.assertRaisesRegex(ValueError, "Unknown or stale"):
            assess_findings((high,), (("0" * 64),))
        with self.assertRaisesRegex(ValueError, "Only a high-confidence block"):
            assess_findings((warning,), (warning.finding_id,))


if __name__ == "__main__":
    unittest.main()
