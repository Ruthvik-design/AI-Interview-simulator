import json
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs
from uuid import uuid4
from config import (HOST, PORT, MODEL, OLLAMA_URL, MAX_QUESTIONS, FOLLOWUP_BELOW, SESSION_SECONDS, KEYS, LOCKS)
from errors import AuthError, Forbidden
from database import (connection, now, create_user, hash_password, get_setting, set_setting, delete_setting, report, init_db)
from prompts.agent_prompts import AGENTS
from agents.interview_agents import question_agent, evaluator_agent, followup_agent, feedback_agent, improvement_agent
from services.progress_service import complete_interview_progress, get_user_progress
from templates import HTML

class Handler(BaseHTTPRequestHandler):
    def send_json(self, obj, status=200, headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # ---- login helpers ----
    def token(self):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        return cookie['session'].value if 'session' in cookie else ''

    def current_user(self):
        token = self.token()
        if not token:
            return None
        with connection() as con:
            row = con.execute('''SELECT u.id,u.username,u.display_name,u.role,s.created FROM sessions s
                                 JOIN users u ON u.id=s.user_id WHERE s.token=?''', (token,)).fetchone()
            if row is None:
                return None
            if time.time() - row['created'] > SESSION_SECONDS:
                con.execute('DELETE FROM sessions WHERE token=?', (token,))
                return None
        user = dict(row)
        del user['created']
        return user

    def require(self, admin=False):
        user = self.current_user()
        if user is None:
            raise AuthError('Please log in.')
        if admin and user['role'] != 'admin':
            raise Forbidden('Admin access required.')
        return user

    def login_headers(self, user_id):
        token = secrets.token_hex(32)
        with connection() as con:
            con.execute('INSERT INTO sessions (token,user_id,created) VALUES (?,?,?)', (token, user_id, time.time()))
        return {'Set-Cookie': f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}'}

    @staticmethod
    def own_or_admin(user, row):
        if row is None or (user['role'] != 'admin' and row['user_id'] != user['id']):
            raise ValueError('Interview not found.')

    # ---- GET ----
    def do_GET(self):
        try:
            path, _, query = self.path.partition('?')
            if path == '/':
                data = HTML.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path == '/api/me':
                self.send_json({'user': self.current_user()})
            elif path == '/api/history':
                user = self.require()
                with connection() as con:
                    rows = con.execute('''SELECT i.*, (SELECT COUNT(*) FROM answers a WHERE a.interview_id=i.id) answered
                                          FROM interviews i WHERE (?=1 OR i.user_id=?)
                                          ORDER BY i.created_at DESC LIMIT 50''',
                                       (1 if user['role'] == 'admin' else 0, user['id'])).fetchall()
                    self.send_json([dict(r) for r in rows])
            elif path == '/api/report':
                user = self.require()
                interview_id = parse_qs(query).get('id', [''])[0]
                with connection() as con:
                    owner = con.execute('SELECT user_id FROM interviews WHERE id=?', (interview_id,)).fetchone()
                    self.own_or_admin(user, owner)
                    result = report(con, interview_id)
                    result['progress'] = get_user_progress(owner['user_id'], interview_id)
                    self.send_json(result)
            elif path == '/api/admin/overview':
                self.require(admin=True)
                self.send_json(self.overview())
            elif path == '/api/admin/export':
                self.require(admin=True)
                with connection() as con:
                    dump = {'exported_at': now(),
                            'interviews': [dict(r) for r in con.execute('SELECT * FROM interviews')],
                            'answers': [dict(r) for r in con.execute('SELECT * FROM answers')],
                            'feedback': [dict(r) for r in con.execute('SELECT * FROM feedback')]}
                self.send_json(dump, headers={'Content-Disposition': 'attachment; filename="interview_data.json"'})
            else:
                self.send_json({'error': 'Not found'}, 404)
        except AuthError as e:
            self.send_json({'error': str(e)}, 401)
        except Forbidden as e:
            self.send_json({'error': str(e)}, 403)
        except ValueError as e:
            self.send_json({'error': str(e)}, 404)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)

    def overview(self):
        with connection() as con:
            count = lambda t: con.execute(f'SELECT COUNT(*) c FROM {t}').fetchone()['c']
            users = [dict(r) for r in con.execute('''SELECT u.id,u.username,u.display_name,u.role,u.created_at,
                     (SELECT COUNT(*) FROM interviews i WHERE i.user_id=u.id) interviews FROM users u ORDER BY u.id''')]
            feedback = [dict(r) for r in con.execute('''SELECT f.*, u.username FROM feedback f
                        JOIN users u ON u.id=f.user_id ORDER BY f.id DESC LIMIT 100''')]
            examples = [dict(r) for r in con.execute('SELECT * FROM training_examples ORDER BY id DESC')]
            stats = {'users': count('users'), 'interviews': count('interviews'),
                     'answers': count('answers'), 'feedback': count('feedback')}
        agents = [{'key': k, 'label': a['label'], 'prompt': get_setting('prompt_' + k, a['prompt']),
                   'custom': get_setting('prompt_' + k) is not None} for k, a in AGENTS.items()]
        return {'stats': stats, 'users': users, 'feedback': feedback, 'examples': examples, 'agents': agents,
                'model': get_setting('model', MODEL), 'followup_below': FOLLOWUP_BELOW}

    # ---- POST ----
    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', 0))
            if size > 40000 or size <= 0:
                raise ValueError('Invalid request size.')
            data = json.loads(self.rfile.read(size))
            route = self.path
            if route == '/api/register':
                username = str(data.get('username', '')).strip()
                display = str(data.get('display_name', '')).strip()[:80] or username
                password = str(data.get('password', ''))
                if not re.fullmatch(r'[A-Za-z0-9_.-]{3,30}', username):
                    raise ValueError('Username must be 3-30 letters, numbers, dots, dashes or underscores.')
                if not 6 <= len(password) <= 100:
                    raise ValueError('Password must be 6-100 characters.')
                try:
                    with connection() as con:
                        create_user(con, username, display, password, 'candidate')   # self-registration is ALWAYS candidate
                        user_id = con.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()['id']
                except sqlite3.IntegrityError:
                    raise ValueError('That username is already taken.')
                self.send_json({'user': {'id': user_id, 'username': username, 'display_name': display, 'role': 'candidate'}},
                               headers=self.login_headers(user_id))
            elif route == '/api/login':
                username = str(data.get('username', '')).strip()
                password = str(data.get('password', ''))
                with connection() as con:
                    row = con.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                if row is None or not hmac.compare_digest(hash_password(password, row['salt']), row['password_hash']):
                    raise AuthError('Wrong username or password.')
                self.send_json({'user': {'id': row['id'], 'username': row['username'],
                                         'display_name': row['display_name'], 'role': row['role']}},
                               headers=self.login_headers(row['id']))
            elif route == '/api/logout':
                with connection() as con:
                    con.execute('DELETE FROM sessions WHERE token=?', (self.token(),))
                self.send_json({'ok': True}, headers={'Set-Cookie': 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            elif route == '/api/start':
                user = self.require()
                role = str(data.get('role', '')).strip()[:100]
                experience = str(data.get('experience', 'Fresher'))[:50]
                kind = str(data.get('kind', 'Technical'))[:50]
                total = int(data.get('total', 5))
                if not role or total < 1 or total > MAX_QUESTIONS:
                    raise ValueError('Job role or question count is invalid.')
                question = question_agent(role, experience, kind, [])
                interview_id = uuid4().hex
                with connection() as con:
                    con.execute('''INSERT INTO interviews (id,name,role,experience,kind,total,status,created_at,user_id)
                                   VALUES (?,?,?,?,?,?,?,?,?)''',
                                (interview_id, user['display_name'], role, experience, kind, total, 'active', now(), user['id']))
                    con.execute('INSERT INTO questions (interview_id,current_question,is_followup) VALUES (?,?,0)', (interview_id, question))
                self.send_json({'id': interview_id, 'question': question})
            elif route == '/api/answer':
                user = self.require()
                interview_id = str(data.get('id', ''))
                answer = str(data.get('answer', '')).strip()
                if not answer or len(answer) > 5000:
                    raise ValueError('Answer must be 1–5000 characters.')
                with LOCKS.setdefault(interview_id, threading.Lock()):
                    with connection() as con:
                        info = con.execute('SELECT * FROM interviews WHERE id=?', (interview_id,)).fetchone()
                        self.own_or_admin(user, info)
                        q = con.execute('SELECT * FROM questions WHERE interview_id=?', (interview_id,)).fetchone()
                        if info['status'] != 'active' or not q:
                            raise ValueError('Active interview not found.')
                        history = [dict(x) for x in con.execute('SELECT question,answer FROM answers WHERE interview_id=? ORDER BY id', (interview_id,))]
                        current, was_followup = q['current_question'], bool(q['is_followup'])
                        # Agent 2: evaluate -> Agent 4: write feedback
                        scores = evaluator_agent(info['role'], info['kind'], current, answer)
                        feedback = feedback_agent(info['role'], info['kind'], current, answer, scores)
                        updated = history + [{'question': current, 'answer': answer}]
                        done = len(updated) >= info['total']
                        next_q, is_followup = None, False
                        if not done:
                            average = sum(scores.values()) / len(KEYS)
                            if not was_followup and average < FOLLOWUP_BELOW:
                                # Agent 3: follow-up on the weak area (never two follow-ups in a row)
                                next_q = followup_agent(info['role'], info['kind'], current, answer, scores)
                                is_followup = True
                            else:
                                # Agent 1: brand-new question
                                next_q = question_agent(info['role'], info['experience'], info['kind'], updated)
                        con.execute('''INSERT INTO answers (interview_id,question,answer,feedback,scores,created_at,is_followup)
                                       VALUES (?,?,?,?,?,?,?)''',
                                    (interview_id, current, answer, feedback, json.dumps(scores), now(), int(was_followup)))
                        if done:
                            con.execute("UPDATE interviews SET status='completed' WHERE id=?", (interview_id,))
                            con.execute('DELETE FROM questions WHERE interview_id=?', (interview_id,))
                        else:
                            con.execute('UPDATE questions SET current_question=?, is_followup=? WHERE interview_id=?',
                                        (next_q, int(is_followup), interview_id))
                if done:
                    complete_interview_progress(user['id'], interview_id)
                self.send_json({'done': done, 'question': next_q, 'is_followup': is_followup,
                                'number': len(updated) + 1, 'scores': scores, 'feedback': feedback})
            elif route == '/api/finish':
                user = self.require()
                interview_id = str(data.get('id', ''))
                with connection() as con:
                    self.own_or_admin(user, con.execute('SELECT user_id FROM interviews WHERE id=?', (interview_id,)).fetchone())
                    result = con.execute("UPDATE interviews SET status='completed' WHERE id=? AND status='active'", (interview_id,))
                    if result.rowcount == 0:
                        raise ValueError('Active interview not found.')
                    con.execute('DELETE FROM questions WHERE interview_id=?', (interview_id,))
                complete_interview_progress(user['id'], interview_id)
                self.send_json({'ok': True})
            elif route == '/api/feedback':
                user = self.require()
                comment = str(data.get('comment', '')).strip()[:1000]
                category = str(data.get('category', 'Other'))[:50]
                rating = int(data.get('rating', 3))
                interview_id = data.get('interview_id')
                if not comment or not 1 <= rating <= 5:
                    raise ValueError('Please give a comment and a rating from 1 to 5.')
                with connection() as con:
                    con.execute('INSERT INTO feedback (user_id,interview_id,category,rating,comment,created_at) VALUES (?,?,?,?,?,?)',
                                (user['id'], str(interview_id) if interview_id else None, category, rating, comment, now()))
                self.send_json({'ok': True})
            elif route.startswith('/api/admin/'):
                admin = self.require(admin=True)
                self.admin_post(route, data, admin)
            else:
                self.send_json({'error': 'Not found'}, 404)
        except AuthError as e:
            self.send_json({'error': str(e)}, 401)
        except Forbidden as e:
            self.send_json({'error': str(e)}, 403)
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send_json({'error': str(e)}, 400)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)

    def admin_post(self, route, data, admin):
        if route in ('/api/admin/prompt', '/api/admin/prompt/reset'):
            agent = str(data.get('agent', ''))
            if agent not in AGENTS:
                raise ValueError('Unknown agent.')
            if route.endswith('/reset'):
                delete_setting('prompt_' + agent)
            else:
                prompt = str(data.get('prompt', '')).strip()
                if not 20 <= len(prompt) <= 4000:
                    raise ValueError('Prompt must be 20-4000 characters.')
                set_setting('prompt_' + agent, prompt)
        elif route == '/api/admin/model':
            name = str(data.get('model', '')).strip()
            if not re.fullmatch(r'[\w.:/-]{1,80}', name):
                raise ValueError('Invalid model name.')
            set_setting('model', name)
        elif route == '/api/admin/role':
            user_id, role = int(data.get('user_id', 0)), str(data.get('role', ''))
            if role not in ('admin', 'candidate'):
                raise ValueError('Role must be admin or candidate.')
            if user_id == admin['id']:
                raise ValueError('You cannot change your own role.')
            with connection() as con:
                if con.execute('UPDATE users SET role=? WHERE id=?', (role, user_id)).rowcount == 0:
                    raise ValueError('User not found.')
        elif route == '/api/admin/example':
            question = str(data.get('question', '')).strip()[:500]
            sample = str(data.get('sample_answer', '')).strip()[:2000]
            score = float(data.get('ideal_score', -1))
            if not question or not sample or not 0 <= score <= 10:
                raise ValueError('Question, sample answer and a score from 0 to 10 are required.')
            with connection() as con:
                con.execute('INSERT INTO training_examples (question,sample_answer,ideal_score,note,created_by,created_at) VALUES (?,?,?,?,?,?)',
                            (question, sample, score, str(data.get('note', '')).strip()[:300], admin['id'], now()))
        elif route == '/api/admin/example/delete':
            with connection() as con:
                con.execute('DELETE FROM training_examples WHERE id=?', (int(data.get('id', 0)),))
        else:
            self.send_json({'error': 'Not found'}, 404)
            return
        self.send_json({'ok': True})
