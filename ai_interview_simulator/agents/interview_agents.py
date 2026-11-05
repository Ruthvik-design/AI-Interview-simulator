import json
import re
from config import KEYS
from database import connection, get_setting
from services.ollama_service import ollama
from prompts.agent_prompts import AGENTS

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


def question_agent(role, experience, kind, history):
    previous = [{'question': a['question'], 'answer': a['answer']} for a in history]
    result = run_agent('question', {'role': role, 'experience': experience, 'interview_type': kind,
                                    'previous_exchanges': previous})
    question = str(result.get('question', '')).strip()
    if not question:
        raise RuntimeError('The Question Generator did not produce a question. Please retry.')
    return question[:1000]


def evaluator_agent(role, kind, question, answer):
    with connection() as con:   # admin "training": the 3 newest examples guide the scoring
        rows = con.execute('SELECT question,sample_answer,ideal_score FROM training_examples ORDER BY id DESC LIMIT 3').fetchall()
    payload = {'role': role, 'interview_type': kind, 'question': question, 'answer': answer}
    if rows:
        payload['calibration_examples'] = [dict(r) for r in rows]
    result = run_agent('evaluator', payload)
    scores = result.get('scores', {})
    try:
        return {k: round(max(0, min(10, float(scores[k]))), 1) for k in KEYS}
    except (KeyError, ValueError, TypeError) as e:
        raise RuntimeError('The Answer Evaluator returned invalid scores. Please retry.') from e


def followup_agent(role, kind, question, answer, scores):
    weakest = min(scores, key=scores.get)
    result = run_agent('followup', {'role': role, 'interview_type': kind, 'original_question': question,
                                    'answer': answer, 'weakest_area': weakest, 'scores': scores})
    text = str(result.get('question', '')).strip()
    if not text:
        raise RuntimeError('The Follow-up Questioner did not produce a question. Please retry.')
    return text[:1000]


def feedback_agent(role, kind, question, answer, scores):
    result = run_agent('feedback', {'role': role, 'interview_type': kind, 'question': question,
                                    'answer': answer, 'scores': scores})
    return str(result.get('feedback', 'No feedback provided.'))[:2500]

def improvement_agent(role, experience, previous_score, current_score, previous_averages, current_averages):
    """Create an actionable plan from the candidate's score trend and weak areas."""
    result = run_agent('improvement', {
        'role': role, 'experience': experience,
        'previous_score_out_of_10': previous_score,
        'current_score_out_of_10': current_score,
        'previous_category_scores': previous_averages,
        'current_category_scores': current_averages,
        'instructions': 'Create a practical plan with 3-5 prioritized actions, practice tasks, and measurable goals for the next test.'
    })
    plan = result.get('plan', '')
    if isinstance(plan, list):
        plan = '\n'.join('- ' + str(x) for x in plan)
    plan = str(plan).strip()
    if not plan:
        raise RuntimeError('Improvement Coach returned an empty plan.')
    return plan[:5000]
