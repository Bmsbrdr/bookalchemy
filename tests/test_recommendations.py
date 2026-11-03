"""OpenRouter tests with mocked requests."""

import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from recommendations import (
    RecommendationError, format_recommendation, recommend_books,
    remove_generated_rating,
)


class RecommendationClientTest(unittest.TestCase):
    """Tests for OpenRouter requests and errors."""

    def setUp(self):
        """Set up a sample book."""
        self.books = [SimpleNamespace(title='Example', rating=8,
                                      author=SimpleNamespace(name='Writer'))]

    def test_safe_formatting_and_rating_removal(self):
        """Check formatting, HTML escaping, and rating removal."""
        value = '**Title:** A Book\n**Rating (out of 10):** 9\nTry *this book*.'
        cleaned = remove_generated_rating(value)
        self.assertNotIn('Rating', cleaned)
        rendered = str(format_recommendation(cleaned + '<script>alert(1)</script>'))
        self.assertIn('<strong>Title:</strong>', rendered)
        self.assertIn('<em>this book</em>', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    @patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key',
                              'OPENROUTER_MODEL': 'openrouter/free'})
    @patch('recommendations.urlopen')
    def test_request_and_response(self, network):
        """Check the request payload and response text."""
        network.return_value.__enter__.return_value = io.StringIO(json.dumps(
            {'choices': [{'message': {'content': 'Read another book.'}}]}
        ))
        self.assertEqual(recommend_books(self.books), 'Read another book.')
        request = network.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], 'openrouter/free')
        history = json.loads(payload['messages'][1]['content'].split('\n', 1)[1])
        self.assertEqual(history[0]['rating_out_of_10'], 8)
        self.assertEqual(request.full_url, 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(network.call_args.kwargs['timeout'], 45)

    @patch.dict('os.environ', {'OPENROUTER_API_KEY': ''})
    @patch('recommendations.urlopen')
    def test_missing_key(self, network):
        """Check that a missing key prevents requests."""
        with self.assertRaisesRegex(RecommendationError, 'not configured'):
            recommend_books(self.books)
        network.assert_not_called()

    @patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key',
                              'OPENROUTER_MODEL': 'paid-model'})
    @patch('recommendations.urlopen')
    def test_paid_model_rejected(self, network):
        """Check that paid models are rejected."""
        with self.assertRaises(RecommendationError):
            recommend_books(self.books)
        network.assert_not_called()

    @patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key',
                              'OPENROUTER_MODEL': 'example/model:free'})
    @patch('recommendations.urlopen')
    def test_provider_errors(self, network):
        """Check rate limits, timeouts, and invalid responses."""
        network.side_effect = HTTPError('https://openrouter.ai', 429, 'Limit', {}, None)
        with self.assertRaisesRegex(RecommendationError, 'rate limited'):
            recommend_books(self.books)
        network.side_effect = TimeoutError()
        with self.assertRaisesRegex(RecommendationError, 'in time'):
            recommend_books(self.books)
        network.side_effect = None
        network.return_value.__enter__.return_value = io.StringIO('{}')
        with self.assertRaisesRegex(RecommendationError, 'no usable'):
            recommend_books(self.books)
