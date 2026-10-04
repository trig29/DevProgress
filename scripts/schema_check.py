"""Offline validator for the JSON Schema keywords used by this project.

No external packages. This is a documented subset, not a general JSON Schema engine.
"""
import math
import re
from datetime import date, datetime


def validate_schema(value, schema, root=None, path='$'):
    root = schema if root is None else root
    if '$ref' in schema:
        target = root
        for key in schema['$ref'].removeprefix('#/').split('/'):
            target = target[key.replace('~1', '/').replace('~0', '~')]
        return validate_schema(value, target, root, path)
    errors = []
    for rule in schema.get('allOf', []):
        errors.extend(validate_schema(value, rule, root, path))
    if 'if' in schema:
        branch = 'then' if not validate_schema(value, schema['if'], root, path) else 'else'
        errors.extend(validate_schema(value, schema.get(branch, {}), root, path))
    if 'const' in schema and value != schema['const']:
        errors.append(f'{path}: expected {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{path}: invalid enum value {value!r}')
    types = schema.get('type', [])
    types = [types] if isinstance(types, str) else types
    predicates = {
        'null': lambda x: x is None, 'boolean': lambda x: isinstance(x, bool),
        'string': lambda x: isinstance(x, str), 'object': lambda x: isinstance(x, dict),
        'array': lambda x: isinstance(x, list),
        'number': lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x),
        'integer': lambda x: isinstance(x, int) and not isinstance(x, bool),
    }
    if types and not any(predicates[t](value) for t in types):
        return errors + [f'{path}: expected {types}']
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                errors.append(f'{path}: missing {key}')
        props = schema.get('properties', {})
        for key, child in value.items():
            if key in props:
                errors.extend(validate_schema(child, props[key], root, f'{path}.{key}'))
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}: unexpected {key}')
            elif isinstance(schema.get('additionalProperties'), dict):
                errors.extend(validate_schema(child, schema['additionalProperties'], root, f'{path}.{key}'))
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append(f'{path}: too few items')
        for index, child in enumerate(value):
            errors.extend(validate_schema(child, schema.get('items', {}), root, f'{path}[{index}]'))
    if isinstance(value, str):
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(f'{path}: pattern mismatch')
        try:
            if schema.get('format') == 'date':
                date.fromisoformat(value)
            elif schema.get('format') == 'date-time':
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    raise ValueError('timezone required')
        except ValueError:
            errors.append(f'{path}: invalid {schema["format"]}')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for keyword, compare in [('minimum', lambda a,b:a>=b), ('maximum', lambda a,b:a<=b), ('exclusiveMinimum', lambda a,b:a>b), ('exclusiveMaximum', lambda a,b:a<b)]:
            if keyword in schema and not compare(value, schema[keyword]):
                errors.append(f'{path}: violates {keyword}')
    return errors
