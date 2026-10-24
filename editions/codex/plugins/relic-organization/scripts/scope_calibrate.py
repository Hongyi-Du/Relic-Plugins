"""One preregistered development episode on the existing tenant-ledger task."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.benchmark import BASELINE, BRIEFS, bundle_hash
from relic_org.scope_evolution.codex_episode import create_executor, execution_contract, write_json
from relic_org.scope_evolution.natural_pilot import digest, immutable, read
from relic_org.scope_evolution.natural_recovery import auth_validity_receipt
from relic_org.scope_evolution.calibration_probe import (
    SCRIPT_NAME, model_isolation_contract, model_isolation_evidence, probe_source)


def calibrate(directory):
    from relic_org.scope_evolution.natural_pilot import calibration_actual_work, calibration_actual_work_contract
    directory = Path(directory).resolve()
    plan_path = directory / 'calibration-plan.json'
    envelope = read(plan_path)
    plan = envelope['plan']
    contract = execution_contract()
    if (digest(plan) != envelope['sha256'] or plan['execution_contract'] != contract or
            plan.get('episodes') != 1 or plan.get('task_id') != 'tenant-ledger' or
            plan.get('development_only') is not True or plan.get('counts_as_pilot') is not False or
            plan.get('actual_work_contract') != calibration_actual_work_contract() or
            plan.get('model_isolation_contract') != model_isolation_contract()):
        raise ValueError('A matching immutable one-episode development calibration plan is required.')
    output = directory / 'executor'
    if output.exists() and any(output.iterdir()):
        raise ValueError('Calibration executor already exists; never repeat an uncertain or completed call.')
    budget = plan['budget']
    auth = auth_validity_receipt(budget['wall_seconds'] + 600)
    immutable(directory / 'auth-lifetime.json', auth)
    product = directory / 'product'
    product.mkdir(exist_ok=True)
    for name, text in BASELINE.items():
        path = product / name
        if path.exists() and path.read_text(encoding='utf-8') != text:
            raise ValueError('Existing calibration product differs from the original starter.')
        if not path.exists():
            path.write_text(text, encoding='utf-8')
    requirements = ('Existing tenant-ledger development task. Deliver all three components together.\n'
        + '\n\n'.join(name + ': ' + brief for name, brief in BRIEFS.items())
        + '\n\nhandle(state, request) returns status/body; post/list/export/revoke. '
          'State has entries and grants. Work only in this product workspace using the provided local toolchain. '
          'Check the resulting behavior locally. The independent grader is external.')
    requirements += ('\nDevelopment-only harness check: before the business changes, run '
        '`CODEX_HOME=/scope-home python calibration_sandbox_check.py` through your own terminal tool. '
        'Do not edit that supplied check script. It verifies that two public TCP connections and opening '
        'the private login file are denied; it never reads or prints credential contents. '
        'If that isolation check fails, stop and report it without changing the check or proceeding with the product. '
        'Then implement the product, run `python -m py_compile api.py ledger.py policy.py`, '
        'and check the behavior with local assertions or tests that you author.')
    (product / 'REQUIREMENTS.txt').write_text(requirements, encoding='utf-8')
    prompt = 'Implement the existing product according to REQUIREMENTS.txt, then check the behavior locally.'
    initial_manifest = directory / 'product-initial.json'
    initial_product = {name: hashlib.sha256((product / name).read_bytes()).hexdigest() for name in BASELINE}
    immutable(initial_manifest, initial_product)
    executor = create_executor(product, output, model=plan['model'], effort=plan['effort'])
    try:
        probes = read(output / 'network-canary.json')['probes']
        supplied_probe = probe_source(probes).encode('utf-8')
        (product / SCRIPT_NAME).write_bytes(supplied_probe)
        source_artifact = directory / 'model-probe-source.py'
        with source_artifact.open('xb') as stream:
            stream.write(supplied_probe)
        immutable(directory / 'calibration-input.json', {
            'task_source': str(Path(__file__).resolve().parents[1] / 'relic_org/benchmark.py'),
            'original_starter_bundle': bundle_hash(BASELINE), 'requirements': requirements, 'prompt': prompt,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'plan_sha256': envelope['sha256'], 'development_only': True, 'counts_as_pilot': False,
            'model_probe_sha256': hashlib.sha256(supplied_probe).hexdigest(),
            'model_probe_targets': probes})
        terminal = executor.run([{'type': 'text', 'text': prompt}], budget)
    finally:
        executor.close()
    final_manifest = directory / 'product-final.json'
    final_product = {name: hashlib.sha256((product / name).read_bytes()).hexdigest()
        for name in BASELINE if (product / name).is_file()}
    immutable(final_manifest, final_product)
    raw_rpc = output / 'rpc-events.jsonl'
    events = [json.loads(line) for line in raw_rpc.read_text(encoding='utf-8').splitlines() if line.strip()]
    actual_work = calibration_actual_work(events, thread_id=terminal['thread_id'],
        turn_id=terminal.get('turn_id'), initial_product=initial_product, final_product=final_product)
    work_path = directory / 'actual-work.json'
    immutable(work_path, actual_work)
    probe_file = product / SCRIPT_NAME
    isolation = model_isolation_evidence(events, thread_id=terminal['thread_id'], turn_id=terminal.get('turn_id'),
        probes=probes, script_unchanged=probe_file.is_file() and probe_file.read_bytes() == supplied_probe)
    isolation_path = directory / 'model-isolation.json'
    immutable(isolation_path, isolation)
    accepted = (terminal.get('status') == 'completed' and
        (terminal.get('terminal') or {}).get('status') == 'completed' and
        terminal.get('budget_expiry') is None and not terminal.get('stop_required') and
        not (terminal.get('contamination') or {}).get('invalid') and
        terminal['elapsed_seconds'] < budget['wall_seconds'] and terminal['tool_actions'] < budget['tool_actions'] and
        actual_work['completed_commands'] and actual_work['successful_local_checks'] and
        actual_work['changed_product_files'] and isolation['passed'])
    receipt = {'schema': 'scope-calibration-v1', 'status': 'accepted' if accepted else 'failed',
        'development_only': True, 'counts_as_pilot': False, 'plan_path': str(plan_path),
        'plan_sha256': envelope['sha256'], 'budget': budget, 'thread_id': terminal['thread_id'],
        'turn_id': terminal.get('turn_id'), 'executor_receipt': str(output / 'terminal.json'),
        'execution_contract': contract, 'execution_contract_sha256': digest(contract),
        'token_usage': terminal.get('token_usage'), 'token_usage_report': terminal.get('token_usage_report'),
        'raw_rpc': str(raw_rpc), 'initial_product_manifest': str(initial_manifest),
        'final_product_manifest': str(final_manifest),
        'product_workspace': str(product),
        'preflight_isolation': str(output / 'network-canary.json'),
        'model_probe_source_artifact': str(source_artifact),
        'actual_work': {**actual_work, 'evidence_artifact': str(work_path)},
        'actual_work_sha256': digest(actual_work),
        'actual_work_contract_sha256': plan['actual_work_contract_sha256'],
        'model_isolation': {**isolation, 'evidence_artifact': str(isolation_path)},
        'model_isolation_sha256': digest(isolation),
        'model_isolation_contract_sha256': plan['model_isolation_contract_sha256'],
        'elapsed_seconds': terminal['elapsed_seconds'], 'tool_actions': terminal['tool_actions']}
    immutable(directory / 'calibration-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    arguments = parser.parse_args()
    try:
        result = calibrate(arguments.run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result['status'] == 'accepted' else 2)
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'stopped', 'reason': str(error)}, ensure_ascii=False))
        raise SystemExit(2)
