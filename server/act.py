"""The LLM call and the actions it may pick (rung 7).

The model is the llama.cpp server on the z170, OpenAI-compatible, served to the tailnet at http://z170:8080.
It answers with one JSON object {"action", "text"}; the action must be on ACTIONS, or nothing runs.
"""
import datetime, json, os, urllib.request

ACTIONS = ('say', 'note', 'none')

SYSTEM_PROMPT = (
    'You turn one short spoken instruction, transcribed by speech-to-text, into one action. '
    'Answer with only a JSON object {"action": ..., "text": ...}. The actions are: '
    '"note" - keep something for later; text is the note, written plainly. '
    '"say" - speak a reply aloud through the speaker; text is what to say. '
    '"none" - anything else, including requests you cannot carry out; text is your answer, spoken aloud too. '
    'A spoken text is one sentence of at most 15 words. '
    'You cannot control lights, devices or anything other than these three actions.'
)


def ask(text, url, timeout_s=10):
    """Returns the model's raw answer; raises OSError on an HTTP error or timeout."""
    body = {
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': text}],
        'temperature': 0,
        'response_format': {'type': 'json_object'},
        'chat_template_kwargs': {'enable_thinking': False},
    }
    req = urllib.request.Request(url.rstrip('/') + '/v1/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        return json.load(r)['choices'][0]['message']['content']


def parse(answer):
    """Returns (action, text); raises ValueError unless the answer is a JSON object with an allowed action."""
    try:
        obj = json.loads(answer)
    except json.JSONDecodeError as e:
        raise ValueError('not JSON: %r' % answer[:80]) from e
    if not isinstance(obj, dict) or not isinstance(obj.get('text'), str):
        raise ValueError('no text: %r' % answer[:80])
    if obj.get('action') not in ACTIONS:
        raise ValueError('action not allowed: %r' % obj.get('action'))
    return obj['action'], obj['text']


def run(action, text, notes_path):
    """`say` and `none` do nothing here: the receiver sends their text to the board as phones (speak.py)."""
    if action == 'note':
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        with open(notes_path, 'a') as f:
            f.write('%s %s\n' % (datetime.datetime.now().isoformat(timespec='seconds'), text))
