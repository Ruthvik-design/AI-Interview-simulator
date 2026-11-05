import json
import urllib.error
import urllib.request
from config import OLLAMA_URL, MODEL
from database import get_setting

def ollama(messages, temperature=0.5):
    model = get_setting('model', MODEL)
    body = json.dumps({'model': model, 'messages': messages, 'stream': False,
                       'options': {'temperature': temperature}}).encode()
    req = urllib.request.Request(OLLAMA_URL, body, {'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=150) as res:
            result = json.load(res)
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f'Cannot reach Ollama ({model}). Start Ollama and run "ollama pull {model}". Details: {e}') from e
    content = result.get('message', {}).get('content', '').strip()
    if not content:
        raise RuntimeError('Ollama returned an empty response. Check the selected model.')
    return content


def run_agent(name, payload):
    """Run one agent: its (admin-editable) prompt + its fixed output format -> parsed JSON."""
    agent = AGENTS[name]
    prompt = get_setting('prompt_' + name, agent['prompt'])
    system = prompt + '\n' + agent['format'] + '\nRespond ONLY with a valid JSON object. No markdown.'
    raw = ollama([{'role': 'system', 'content': system},
                  {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], agent['temp'])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.S)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    raise RuntimeError(f'The {agent["label"]} returned invalid JSON. Please retry your action.')
