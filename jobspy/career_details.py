"""Fresh detail lookup for previously discovered board URLs; no model or cache."""
import json
import re
import sys
from urllib.parse import urlsplit, parse_qs
from jobspy.model import ScraperInput
from jobspy.util import create_session, RequestsRotating, TLSRotating


def fetch(url):
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    config = ScraperInput(fetch_description=True, verbose=0)
    if host in ('linkedin.com', 'www.linkedin.com') and (m := re.fullmatch(r'/jobs/view/(\d+)/?', p.path)):
        from jobspy.linkedin import LinkedIn
        from jobspy.linkedin.constant import headers
        scraper = LinkedIn()
        scraper.scraper_input = config
        scraper.session = create_session(RequestsRotating([], clear_cookies=True), config, headers)
        result = scraper._fetch_details(m[1])
    elif host in ('glassdoor.com', 'www.glassdoor.com') and (job_id := parse_qs(p.query).get('jl', [''])[0]).isdigit():
        from jobspy.glassdoor import Glassdoor
        from jobspy.glassdoor.constant import headers
        scraper = Glassdoor()
        scraper.scraper_input = config
        scraper.base_url = 'https://www.glassdoor.com'
        scraper.session = create_session(TLSRotating([]), config, headers)
        scraper._search_variables()  # Normal Glassdoor session initialization, as in scrape().
        result = scraper._fetch_details(['gd-' + job_id]).get('gd-' + job_id, {})
    elif host in ('ziprecruiter.com', 'www.ziprecruiter.com'):
        from jobspy.ziprecruiter import ZipRecruiter
        scraper = ZipRecruiter()
        scraper.scraper_input = config
        scraper.session = create_session(TLSRotating([]), config)
        scraper.session.impersonate = 'safari'
        result = scraper._fetch_details(None, url)
    else:
        return {'url': url, 'description': '', 'error': 'Unsupported board detail URL'}
    description = result.get('description') or ''
    return {'url': url, 'description': description,
            'error': '' if description else 'Board returned no description; see detail diagnostics'}


if __name__ == '__main__':
    try:
        print(json.dumps(fetch(json.load(sys.stdin)['url'])))
    except Exception as exc:
        print(json.dumps({'description': '', 'error': f'{type(exc).__name__}: {exc}'}))
