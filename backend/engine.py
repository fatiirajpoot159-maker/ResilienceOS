"""ResilienceOS: exact single-machine scheduling optimizer.

Time is represented in 30-minute slots. A single oven processes non-preemptive
jobs, and can't work during an outage unless backup is enabled.
Objective: missed-job penalties plus late completion penalties.
All money amounts are simulated PKR inputs provided by the user.
"""
from functools import lru_cache

SLOTS = 24
SLOT_MINUTES = 30


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError('Scenario must be an object.')
    jobs = payload.get('jobs')
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 12:
        raise ValueError('Provide between 1 and 12 jobs.')
    try:
        outage_start = int(payload.get('outage_start', 8))
        outage_duration = int(payload.get('outage_duration', 4))
        late_rate = int(payload.get('late_rate', 250))
        backup = bool(payload.get('backup', False))
    except (ValueError, TypeError):
        raise ValueError('Invalid scenario parameters.')
    if not 0 <= outage_start <= SLOTS or not 0 <= outage_duration <= SLOTS - outage_start:
        raise ValueError('Outage must fall within the 12-hour workday.')
    if not 0 <= late_rate <= 100000:
        raise ValueError('Late fee must be between 0 and 100,000 PKR per slot.')
    normalized = []
    ids = set()
    for i, job in enumerate(jobs):
        try:
            name = str(job['id']).strip()
            duration = int(job['duration'])
            deadline = int(job['deadline'])
            penalty = int(job['missed_penalty'])
        except (TypeError, ValueError, KeyError):
            raise ValueError(f'Invalid job at row {i + 1}.')
        if not name or len(name) > 48 or name in ids:
            raise ValueError('Job names must be unique and 1–48 characters long.')
        if not 1 <= duration <= SLOTS or not 0 <= deadline <= SLOTS or not 0 <= penalty <= 1000000:
            raise ValueError(f'Invalid duration, deadline, or penalty for {name}.')
        ids.add(name)
        normalized.append(dict(id=name, duration=duration, deadline=deadline, missed_penalty=penalty))
    return normalized, outage_start, outage_duration, late_rate, backup


def first_start(at, duration, outage_start, outage_end, backup=False):
    while at + duration <= SLOTS:
        if backup or not (at < outage_end and at + duration > outage_start):
            return at
        at = outage_end
    return None


def evaluate(jobs, schedule, late_rate):
    by_id = {j['id']: j for j in jobs}
    completed = {e['id']: e for e in schedule}
    late_cost, missed_cost = 0, 0
    for job in jobs:
        if job['id'] not in completed:
            missed_cost += job['missed_penalty']
        else:
            late_cost += max(0, completed[job['id']]['end'] - job['deadline']) * late_rate
    return dict(schedule=sorted(schedule, key=lambda j: j['start']), loss=late_cost + missed_cost,
                late_cost=late_cost, missed_cost=missed_cost, completed=len(completed),
                missed=[j['id'] for j in jobs if j['id'] not in completed])


def baseline(jobs, outage_start, outage_end, backup=False):
    result = []
    t = 0
    for job in jobs:
        start = first_start(t, job['duration'], outage_start, outage_end, backup)
        if start is None:
            continue
        end = start + job['duration']
        result.append(dict(id=job['id'], start=start, end=end))
        t = end
    return result


def calculate(payload):
    jobs, outage_start, outage_duration, late_rate, backup = validate(payload)
    outage_end = outage_start + outage_duration
    simple = evaluate(jobs, baseline(jobs, outage_start, outage_end, backup), late_rate)
    n = len(jobs)
    full_mask = (1 << n) - 1
    # DP over completed-job set and current ending time; choosing next scheduled
    # job or stopping and paying missed penalties proves the optimum for this model.
    @lru_cache(None)
    def solve(mask, t):
        missed_all = sum(jobs[i]['missed_penalty'] for i in range(n) if not mask & (1 << i))
        best = (missed_all, ())
        for i, job in enumerate(jobs):
            if mask & (1 << i):
                continue
            start = first_start(t, job['duration'], outage_start, outage_end, backup)
            if start is None:
                continue
            end = start + job['duration']
            rest_cost, rest_path = solve(mask | (1 << i), end)
            current_cost = late_rate * max(0, end - job['deadline'])
            candidate = (current_cost + rest_cost, ((i, start, end),) + rest_path)
            if candidate[0] < best[0] or (candidate[0] == best[0] and len(candidate[1]) > len(best[1])):
                best = candidate
        return best

    score, path = solve(0, 0)
    revised = evaluate(jobs, [dict(id=jobs[i]['id'], start=start, end=end) for i, start, end in path], late_rate)
    assert score == revised['loss'], 'Optimizer consistency failure'
    assert revised['loss'] <= simple['loss'], 'Optimized loss cannot exceed baseline'
    savings = simple['loss'] - revised['loss']
    return {
        'baseline': simple, 'optimized': revised, 'savings': savings,
        'improvement_percent': round(100 * savings / simple['loss'], 1) if simple['loss'] else 0,
        'solver_status': 'OPTIMAL', 'algorithm': 'Exact dynamic programming',
        'scenario': dict(outage_start=outage_start, outage_duration=outage_duration,
                         backup=backup, late_rate=late_rate, slots=SLOTS, minutes_per_slot=SLOT_MINUTES),
        'states_explored': solve.cache_info().currsize,
        'assumptions': [
            'One oven with non-interruptible orders',
            'No oven production during outage unless backup is enabled',
            'Money amounts are illustrative inputs, not real measured losses',
            'Each late half-hour adds the configured lateness fee'
        ]
    }
