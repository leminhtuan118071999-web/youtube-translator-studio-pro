import test from 'node:test';
import assert from 'node:assert/strict';
import { autoTranslationReady, validYouTubeLink } from '../src/lib/auto-translation.ts';

test('accepts supported YouTube links and rejects incomplete or lookalike hosts', () => {
  for (const url of ['https://www.youtube.com/watch?v=abcdefghijk','https://youtu.be/abcdefghijk?t=2','https://m.youtube.com/shorts/abcdefghijk','https://youtube.com/live/abcdefghijk']) assert.equal(validYouTubeLink(url),true,url);
  for (const url of ['', 'https://youtube.com/watch?v=abc', 'https://youtube.com.evil.example/watch?v=abcdefghijk','https://example.com/?v=abcdefghijk','ftp://youtube.com/watch?v=abcdefghijk']) assert.equal(validYouTubeLink(url),false,url);
});
test('only an explicit language choice for the current idle session starts translation', () => {
  const ready={request:{sid:'one',language:'Tiếng Hungary'},sessionId:'one',language:'Tiếng Hungary',url:'https://youtu.be/abcdefghijk',busy:false,running:false,healthy:true};
  assert.equal(autoTranslationReady(ready),true);
  for (const change of [{request:null},{sessionId:'two'},{language:'Tiếng Việt'},{busy:true},{running:true},{healthy:false},{url:''}]) assert.equal(autoTranslationReady({...ready,...change}),false);
});
