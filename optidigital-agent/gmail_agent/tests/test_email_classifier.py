"""Deterministic email-type classification for digest and newsletter mail."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.email_classifier import EmailType, classify_email


class TestEmailClassifier(unittest.TestCase):
    def test_freelancehunt_digest_subject_variants_are_job_digests(self):
        subjects = (
            "Підбірка вакансій «Бекенд» за 16 липня",
            "Підбірка проєктів «Python» за 15 липня",
            "Підбірка проектів «automation, Тестування» за 12 липня",
        )

        for subject in subjects:
            with self.subTest(subject=subject):
                result = classify_email(
                    sender="Freelancehunt <info@freelancehunt.com>",
                    subject=subject,
                    html_body=(
                        '<a href="https://freelancehunt.com/ua/job/synthetic/900001.html">'
                        "Synthetic job</a>"
                    ),
                )
                self.assertEqual(result, EmailType.JOB_DIGEST)

    def test_digest_words_from_an_unapproved_sender_are_not_enough(self):
        result = classify_email(
            sender="Synthetic Offers <offers@example.invalid>",
            subject="Підбірка вакансій «Python» за сьогодні",
            html_body='<a href="https://example.invalid/articles/vacancies">Read</a>',
        )

        self.assertNotEqual(result, EmailType.JOB_DIGEST)

    def test_workua_market_and_article_mail_stays_informational(self):
        newsletters = (
            (
                "Ринок праці у червні: нове дослідження Work.ua",
                "Огляд зарплат, попиту та пропозиції без персональних вакансій.",
            ),
            (
                "Як скласти резюме: статті та поради від Work.ua",
                "Корисні матеріали для пошуку роботи.",
            ),
        )

        for subject, text_body in newsletters:
            with self.subTest(subject=subject):
                result = classify_email(
                    sender="Work.ua <news@work.ua>",
                    subject=subject,
                    text_body=text_body,
                    html_body='<a href="https://www.work.ua/articles/synthetic/">Read</a>',
                )
                self.assertEqual(result, EmailType.INFORMATIONAL_NEWSLETTER)


if __name__ == "__main__":
    unittest.main(verbosity=2)
