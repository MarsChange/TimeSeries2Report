"""Transport checks without network calls or real credentials."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from utils.browser_client import OpenAI, BrowserAPIError, BrowserNetworkError


class BrowserClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenAI('test-key', 'https://provider.example/v1/')

    @patch('utils.browser_client.requests.post')
    def test_complete_and_chat_responses(self, post):
        post.return_value = SimpleNamespace(ok=True, json=lambda: {'choices': [{'message': {'content': 'answer'}}]})
        response = self.client.chat.completions.create(model='model-id', messages=[], response_format={'type':'json_object'}, extra_body={'enable_thinking':False})
        self.assertEqual(response.choices[0].message.content, 'answer')
        self.assertEqual(post.call_args.args[0], 'https://provider.example/v1/chat/completions')
        self.assertFalse(post.call_args.kwargs['json']['stream'])
        self.assertFalse(post.call_args.kwargs['json']['enable_thinking'])
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer test-key')
        chunks = list(self.client.chat.completions.create(model='model-id', messages=[], stream=True))
        self.assertEqual(chunks[0].choices[0].delta.content, 'answer')

    @patch('utils.browser_client.requests.post')
    def test_network_errors_do_not_leak_provider_details(self, post):
        post.side_effect = RuntimeError('sensitive-provider-details')
        with self.assertRaises(BrowserNetworkError) as raised:
            self.client.chat.completions.create(model='model-id', messages=[])
        self.assertNotIn('sensitive-provider-details', str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    @patch('utils.browser_client.requests.post')
    def test_http_and_malformed_responses(self, post):
        post.return_value = SimpleNamespace(ok=False, status_code=401)
        with self.assertRaisesRegex(BrowserAPIError, '401'):
            self.client.chat.completions.create(model='model-id', messages=[])
        for data in ({}, {'choices':[]}, {'choices':[{'message':{'content':None}}]}):
            post.return_value = SimpleNamespace(ok=True, json=lambda data=data: data)
            with self.assertRaises(BrowserAPIError):
                self.client.chat.completions.create(model='model-id', messages=[])


if __name__ == '__main__':
    unittest.main()
