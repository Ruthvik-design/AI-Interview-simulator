"""Persistent candidate score, retest comparison, and AI-generated study plans."""
from database import connection, now, report
from agents.interview_agents import improvement_agent


def _rating(change):
    if change is None:
        return 'Baseline established'
    if change >= 20:
        return 'Outstanding improvement'
    if change >= 10:
        return 'Strong improvement'
    if change > 0:
        return 'Positive improvement'
    if change == 0:
        return 'Maintained performance'
    if change > -10:
        return 'Slight decline'
    return 'Needs focused practice'


def complete_interview_progress(user_id, interview_id):
    """Update the single current score and persist a plan for this completed test."""
    with connection() as con:
        current_row = con.execute('SELECT * FROM interviews WHERE id=? AND user_id=?',
                                  (interview_id, user_id)).fetchone()
        if not current_row:
            return
        current = report(con, interview_id)
        if not current['answers']:
            return  # Do not treat an empty early-finish as a scored attempt.
        prior_row = con.execute('''SELECT i.id FROM interviews i WHERE i.user_id=? AND i.status='completed'
                                   AND i.id<>? AND EXISTS (SELECT 1 FROM answers a WHERE a.interview_id=i.id)
                                   ORDER BY i.created_at DESC LIMIT 1''',
                                (user_id, interview_id)).fetchone()
        previous = report(con, prior_row['id']) if prior_row else None
        prior_score = previous['overall'] if previous else None
        score = current['overall']
        pct = round(((score - prior_score) / prior_score) * 100, 1) if prior_score not in (None, 0) else None
        rating = _rating(pct)
        attempts = con.execute("""SELECT COUNT(*) n FROM interviews i WHERE i.user_id=? AND i.status='completed'
                                AND EXISTS (SELECT 1 FROM answers a WHERE a.interview_id=i.id)""",
                               (user_id,)).fetchone()['n']
        con.execute('''INSERT INTO candidate_progress
                       (user_id,latest_score,previous_score,improvement_pct,progress_rating,attempts,latest_interview_id,updated_at)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET latest_score=excluded.latest_score,
                       previous_score=excluded.previous_score, improvement_pct=excluded.improvement_pct,
                       progress_rating=excluded.progress_rating, attempts=excluded.attempts,
                       latest_interview_id=excluded.latest_interview_id, updated_at=excluded.updated_at''',
                    (user_id, score, prior_score, pct, rating, attempts, interview_id, now()))
        exists = con.execute('SELECT id FROM improvement_plans WHERE interview_id=?', (interview_id,)).fetchone()
        if exists:
            return
        role, experience = current_row['role'], current_row['experience']
        prior_averages = previous['averages'] if previous else {}
        current_averages = current['averages']
    try:
        plan = improvement_agent(role, experience, prior_score, score, prior_averages, current_averages)
    except Exception:
        weak = sorted(current_averages.items(), key=lambda item: item[1])[:2]
        plan = 'Personalized improvement plan:\n' + '\n'.join(
            f'- Practice {key.replace("_", " ")} with two role-specific questions; target at least 1 point higher.'
            for key, _ in weak
        ) + '\n- Complete one timed mock interview and review every answer against the feedback.'
    with connection() as con:
        con.execute('INSERT OR IGNORE INTO improvement_plans (user_id,interview_id,plan,created_at) VALUES (?,?,?,?)',
                    (user_id, interview_id, plan, now()))


def get_user_progress(user_id, interview_id=None):
    with connection() as con:
        row = con.execute('SELECT * FROM candidate_progress WHERE user_id=?', (user_id,)).fetchone()
        if not row:
            return {'attempts': 0, 'latest_score': None, 'previous_score': None,
                    'improvement_pct': None, 'progress_rating': 'No completed interviews', 'plan': None}
        plan_row = None
        if interview_id:
            plan_row = con.execute('SELECT plan FROM improvement_plans WHERE user_id=? AND interview_id=?',
                                   (user_id, interview_id)).fetchone()
        if not plan_row:
            plan_row = con.execute('''SELECT plan FROM improvement_plans WHERE user_id=?
                                      ORDER BY id DESC LIMIT 1''', (user_id,)).fetchone()
        result = dict(row)
        result['plan'] = plan_row['plan'] if plan_row else None
        return result
