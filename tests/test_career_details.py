import unittest
from unittest.mock import patch
from jobspy.career_details import fetch

class DetailsTests(unittest.TestCase):
    def test_unsupported_url_does_not_fetch(self):
        with patch('jobspy.career_details.create_session') as session:
            self.assertIn('Unsupported',fetch('http://127.0.0.1/private')['error'])
            session.assert_not_called()
    def test_glassdoor_uses_normal_initialization_and_exact_id(self):
        with patch('jobspy.glassdoor.Glassdoor') as cls,patch('jobspy.career_details.create_session'):
            cls.return_value._fetch_details.return_value={'gd-123':{'description':'Full JD'}}
            result=fetch('https://www.glassdoor.com/job-listing/j?jl=123')
            cls.return_value._search_variables.assert_called_once()
            cls.return_value._fetch_details.assert_called_once_with(['gd-123'])
            self.assertEqual(result['description'],'Full JD')
    def test_linkedin_exact_id(self):
        with patch('jobspy.linkedin.LinkedIn') as cls,patch('jobspy.career_details.create_session'):
            cls.return_value._fetch_details.return_value={'description':'Full JD'}
            self.assertEqual(fetch('https://www.linkedin.com/jobs/view/123')['description'],'Full JD')
            cls.return_value._fetch_details.assert_called_once_with('123')
