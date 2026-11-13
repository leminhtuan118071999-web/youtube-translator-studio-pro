import unittest
from unittest.mock import patch,MagicMock
from api_clients import generate_text,_read_provider_answer,ProviderEmptyResponse


class VisibleAnswerTests(unittest.TestCase):
    def test_empty_chat_envelope_can_still_contain_responses_answer(self):
        payload=dict(choices=[dict(message=dict(content=None),finish_reason='stop')],output=[
            dict(type='reasoning',content=[dict(type='text',text='hidden')]),
            dict(type='message',role='assistant',content=[dict(type='output_text',text='Bản dịch.')])])
        self.assertEqual(_read_provider_answer(payload,'chat','OpenAI','gpt-6.1-sol'),'Bản dịch.')

    def test_responses_without_choices_remains_supported(self):
        self.assertEqual(_read_provider_answer(dict(output_text='Answer'),'chat','OpenAI','model'),'Answer')

    def test_reasoning_is_never_returned_as_translation(self):
        payload=dict(choices=[dict(message=dict(content='',reasoning_content='hidden chain'),finish_reason='stop')],
                     usage=dict(completion_tokens=2700))
        with self.assertRaises(ProviderEmptyResponse):_read_provider_answer(payload,'chat','OpenAI','gpt-6.1-sol')

    def test_refusal_and_tools_are_not_reclassified_as_empty_retry(self):
        for message,reason in [(dict(content=None,refusal='Refused'),'stop'),
                               (dict(content=None,tool_calls=[dict(id='x')]),'tool_calls'),
                               (dict(content=None),'content_filter')]:
            with self.subTest(reason=reason),self.assertRaises(RuntimeError) as caught:
                _read_provider_answer(dict(choices=[dict(message=message,finish_reason=reason)]),'chat','OpenAI','model')
            self.assertNotIsInstance(caught.exception,ProviderEmptyResponse)

    def test_sol_requests_reasoning_and_output_headroom_only_for_that_model(self):
        response=MagicMock(ok=True,status_code=200)
        response.json.return_value=dict(choices=[dict(message=dict(content='Answer'),finish_reason='stop')])
        with patch('api_clients.validate_base_url',return_value='https://api.openai.com/v1'), \
             patch('api_clients._request',return_value=response) as request:
            for model in ('gpt-6.1-sol','gpt-4.1-mini'):
                self.assertEqual(generate_text('OpenAI','https://api.openai.com/v1',model,'TEST-ONLY','DIRECT_TRANSLATION. Source'),'Answer')
                body=request.call_args.kwargs['json']
                if model=='gpt-6.1-sol':
                    self.assertEqual(body['reasoning_effort'],'low')
                    self.assertGreaterEqual(body['max_completion_tokens'],16384)
                else:self.assertNotIn('reasoning_effort',body)
