"""Synthetic, non-production fixtures shaped like audited Freelancehunt digests."""

from __future__ import annotations


def _job_table(
    *,
    title: str,
    slug: str,
    job_id: int,
    description: str,
    budget: str = "",
    tracking_suffix: str = "?utm_source=email&utm_medium=digest#vacancy",
) -> str:
    budget_html = (
        f'<td class="budget"><strong>{budget}</strong></td>' if budget else ""
    )
    return f"""
    <table class="vacancy-card" role="presentation">
      <tr class="vacancy-heading">
        <td>
          <a class="vacancy-title"
             href="https://freelancehunt.com/ua/job/{slug}/{job_id}.html{tracking_suffix}">
            {title}
          </a>
          <span class="metadata">Remote · Python / Automation</span>
        </td>
        {budget_html}
      </tr>
      <tr class="vacancy-description">
        <td colspan="2">{description}</td>
      </tr>
    </table>
    """


def _digest_noise(*, category: str, campaign: str) -> str:
    """Five links: category, two unsubscribe, and two platform/root links."""
    return f"""
    <a href="https://freelancehunt.com/ua/jobs/{category}/?utm_campaign={campaign}">
      Category
    </a>
    <a href="https://freelancehunt.com/?utm_campaign={campaign}">Freelancehunt</a>
    <a href="https://freelancehunt.com/#top">Home</a>
    <a href="https://freelancehunt.com/unsubscribe?token=synthetic-{campaign}">
      Unsubscribe
    </a>
    <a href="https://freelancehunt.com/unsubscribe?token=synthetic-{campaign}#footer">
      Email preferences
    </a>
    """


DIGEST_TWO_JOBS_HTML = f"""
<!doctype html>
<html>
  <body>
    <table class="digest" role="presentation">
      <tr><td><h1>Підбірка вакансій «Бекенд»</h1></td></tr>
      <tr><td>
        {_job_table(
            title="Synthetic Python automation",
            slug="synthetic-python-automation",
            job_id=900001,
            description="Build an API integration for api.example.invalid.",
            budget="10 000 грн",
        )}
      </td></tr>
      <tr><td>
        {_job_table(
            title="Synthetic QA bot",
            slug="synthetic-qa-bot",
            job_id=900002,
            description="Test a notification bot against qa.example.invalid.",
        )}
      </td></tr>
    </table>
    {_digest_noise(category="programming", campaign="synthetic-two")}
    <img src="https://assets.example.invalid/logo.png" alt="Synthetic logo">
    <img src="https://tracking.example.invalid/pixel.gif" width="1" height="1" alt="">
  </body>
</html>
"""


DIGEST_ONE_JOB_HTML = f"""
<!doctype html>
<html>
  <body>
    <table class="digest" role="presentation">
      <tr><td><h1>Підбірка вакансій «Automation»</h1></td></tr>
      <tr><td>
        {_job_table(
            title="Synthetic Python automation",
            slug="synthetic-python-automation",
            job_id=900001,
            description="Build an API integration for api.example.invalid.",
            tracking_suffix="?utm_source=second_digest&tracking_id=synthetic#details",
        )}
      </td></tr>
    </table>
    {_digest_noise(category="automation", campaign="synthetic-one")}
    <img src="https://assets.example.invalid/banner.jpg" alt="Synthetic banner">
  </body>
</html>
"""


def digest_with_job_count(count: int) -> str:
    jobs = "".join(
        _job_table(
            title=f"Synthetic job {index:02d}",
            slug=f"synthetic-job-{index:02d}",
            job_id=910000 + index,
            description=f"Synthetic description {index:02d} at service.example.invalid.",
        )
        for index in range(1, count + 1)
    )
    return f"<html><body><table><tr><td>{jobs}</td></tr></table></body></html>"
