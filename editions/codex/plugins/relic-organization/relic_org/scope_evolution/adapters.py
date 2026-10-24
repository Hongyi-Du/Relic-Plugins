"""Declarative consumers. Operation implementations are trusted host code."""
import json

from ..store import OrgError, validate_rules


ADAPTER_REVISION = 'declarative-v1'
MAX_JSON_BYTES = 262144


def detached(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise OrgError('Adapter values must be finite JSON.') from error
    if len(encoded.encode('utf-8')) > MAX_JSON_BYTES:
        raise OrgError('Adapter value exceeds the bounded JSON size.')
    return json.loads(encoded)


def format_cents(value, parameters):
    if type(value) is not int:
        raise OrgError('money.format_cents input must be integer cents.')
    sign = '-' if value < 0 else ''
    units, cents = divmod(abs(value), 100)
    return sign + str(units) + '.' + str(cents).zfill(2)


def normalize_whitespace(value, parameters):
    if not isinstance(value, str):
        raise OrgError('text.normalize_whitespace input must be text.')
    return ' '.join(value.split())


def project_fields(value, parameters):
    fields = parameters.get('fields')
    if not isinstance(value, dict) or not isinstance(fields, list) or not all(isinstance(k, str) for k in fields):
        raise OrgError('data.project_fields needs an object and a fields list.')
    return {key: value[key] for key in fields if key in value}


class Adapters:
    def __init__(self, operations=None):
        self.operations = {
            'money.format_cents': {'revision': '1', 'execute': format_cents},
            'text.normalize_whitespace': {'revision': '1', 'execute': normalize_whitespace},
            'data.project_fields': {'revision': '1', 'execute': project_fields},
        }
        for name, operation in (operations or {}).items():
            if not isinstance(name, str) or not name or name in self.operations:
                raise OrgError('Trusted operation IDs must be new nonempty strings.')
            if (not isinstance(operation, dict) or set(operation) != {'revision', 'execute'}
                    or not isinstance(operation['revision'], str) or not operation['revision']
                    or not callable(operation['execute'])):
                raise OrgError('Trusted operation needs an explicit revision and callable.')
            self.operations[name] = dict(operation)

    def validate(self, patch, org):
        kind, payload = patch['kind'], patch['payload']
        detached(payload)
        descriptor = {'adapter_revision': ADAPTER_REVISION, 'kind': kind}
        if kind in ('prompt', 'memory'):
            if set(payload) != {'text'} or not isinstance(payload['text'], str) or not payload['text'].strip():
                raise OrgError('Prompt/memory payload is exactly {text: nonempty string}.')
        elif kind == 'tool':
            if set(payload) - {'operation', 'parameters'} or payload.get('operation') not in self.operations:
                raise OrgError('Tool payload must select a vetted operation; code execution is unavailable.')
            if not isinstance(payload.get('parameters', {}), dict):
                raise OrgError('Operation parameters must be an object.')
            operation = payload['operation']
            parameters = payload.get('parameters', {})
            if operation in ('money.format_cents', 'text.normalize_whitespace') and parameters:
                raise OrgError('This operation does not accept parameters.')
            if operation == 'data.project_fields' and (set(parameters) != {'fields'}
                    or not isinstance(parameters['fields'], list)
                    or not all(isinstance(k, str) for k in parameters['fields'])):
                raise OrgError('Projection parameters are exactly {fields: [strings]}.')
            descriptor.update(operation=operation, operation_revision=self.operations[operation]['revision'])
        elif kind == 'protocol':
            if set(payload) != {'rules'}:
                raise OrgError('Protocol payload is exactly {rules: structured rules}.')
            validate_rules(payload['rules'], org['members'])
        else:
            raise OrgError('No operational adapter for Patch kind: ' + kind)
        return descriptor

    def execute(self, patch, value, org):
        descriptor = self.validate(patch, org)
        if patch['kind'] == 'tool':
            payload = patch['payload']
            result = self.operations[payload['operation']]['execute'](detached(value), detached(payload.get('parameters', {})))
            return {'output': detached(result), 'effect': 'vetted_operation_executed', **descriptor}
        if patch['kind'] in ('prompt', 'memory'):
            return {'output': patch['payload']['text'], 'effect': 'context_content_supplied', **descriptor}
        raise OrgError('Protocol patches take effect at gate admission, not as callable operations.')
