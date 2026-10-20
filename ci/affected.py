"""Conservative, opt-in test-file mappings. An incomplete mapping always runs full CI."""
import fnmatch
import glob
import os
import subprocess

# These can change discovery, dependencies or execution for every test, even if a
# broad repo rule accidentally matches them. Repo-specific shared paths add to this.
SHARED = ['.siso-ci', '.siso-ci*', '.github/*', 'ci/*', '**/package.json', 'package.json',
          '*lock*', '**/*lock*', '*config*', '**/*config*', 'tsconfig*', '**/tsconfig*',
          'pyproject.toml', '**/pyproject.toml', 'requirements*', '**/requirements*',
          'Cargo.toml', '**/Cargo.toml', 'go.mod', '**/go.mod']


def inventory(d, mapping):
    patterns = mapping['test_globs']
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
        raise ValueError('invalid test_globs')
    files = sorted({os.path.relpath(f, d) for p in patterns
                    for f in glob.glob(os.path.join(d, p), recursive=True) if os.path.isfile(f)})
    if not files or any(f.startswith('../') for f in files):
        raise ValueError('empty or external test inventory')
    return files


def select(d, cfg, base, head):
    """Use the merge-base, not base-tip: unrelated base advances are not PR changes.

    Both names of a rename are included (--no-renames); fetch/history/diff errors,
    deleted tests, malformed maps and any unmapped path fall back to the full command.
    The map comes from the runner config, never from an untested PR's config.
    """
    result = dict(cfg)
    receipt = {'mode': 'full', 'reason': 'no mapping', 'selected': None, 'total': None}
    result['selection'] = receipt
    mapping = cfg.get('affected')
    if cfg.get('packages'):
        return select_packages(d, cfg, base, head)
    if not mapping:
        return result
    try:
        changed_cmd = mapping.get('changed')  # the runner itself finds the tests the diff touches (vitest --changed)
        docs_only = not changed_cmd and 'command' not in mapping  # no test map yet: skip docs-only diffs, else full
        if changed_cmd or docs_only:
            files = []
        else:
            files = inventory(d, mapping)
            receipt.update(selected=len(files), total=len(files))
        rules = mapping.get('rules', [])
        if not changed_cmd and not docs_only and (not isinstance(rules, list) or (not rules and not mapping.get('self') and not mapping.get('by_name'))):
            raise ValueError('empty rules')
        if not changed_cmd and not docs_only and (not isinstance(mapping['command'], str) or not mapping['command'].strip()):
            raise ValueError('empty command')
        shared = mapping.get('shared', [])
        if not isinstance(shared, list) or not all(isinstance(p, str) and p for p in shared):
            raise ValueError('invalid shared paths')
        for rule in rules:
            for key in ('paths', 'tests'):
                if not isinstance(rule[key], list) or not rule[key] or not all(isinstance(p, str) and p for p in rule[key]):
                    raise ValueError('invalid rule')
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=d, stderr=subprocess.PIPE).decode('utf-8')
        # Fetch the exact base; do not silently compare against a stale remote branch.
        git('fetch', '-q', 'origin', base)
        ancestor = git('merge-base', base, head).strip()
        changed = git('diff', '--name-only', '--no-renames', '-z', ancestor, head, '--').rstrip('\0').split('\0')
        if not changed or changed == ['']:
            raise ValueError('empty diff')
        ignore = mapping.get('ignore', [])
        if not isinstance(ignore, list) or not all(isinstance(p, str) and p for p in ignore):
            raise ValueError('invalid ignore paths')
        # Shaan, 17 Oct: "we don't even need to do these checks". Paths that hold no code (docs) run nothing at all.
        relevant = [p for p in changed if not any(fnmatch.fnmatchcase(p, g) for g in ignore)]
        if not relevant:
            result.update(setup='', test='true')
            result.pop('sharding', None)
            receipt.update(mode='skip', reason='only docs/ignored paths changed', selected=0)
            return result
        if docs_only:
            receipt['reason'] = 'code changed, no test map: ' + relevant[0]
            return result
        if changed_cmd:
            # Only the repo's own shared paths (lockfile, root config) force a full run; the global SHARED list is too wide.
            for path in relevant:
                if any(fnmatch.fnmatchcase(path, p) for p in shared):
                    receipt['reason'] = 'shared/config: ' + path
                    return result
            result['test'] = changed_cmd
            result.pop('sharding', None)  # a few tests do not need two shards
            receipt.update(mode='changed', reason='tests related to the diff (runner --changed)', selected=None, total=None)
            return result
        chosen = set()
        for path in relevant:
            if any(fnmatch.fnmatchcase(path, p) for p in SHARED + shared):
                receipt['reason'] = 'shared/config: ' + path
                return result
            matches = [r for r in rules if any(fnmatch.fnmatchcase(path, p) for p in r['paths'])]
            if path in files and mapping.get('self'):
                chosen.add(path)
            if mapping.get('by_name'):  # hooks/read-gate.mjs -> tests/read-gate.test.mjs
                stem = os.path.basename(path).split('.')[0]
                chosen.update(f for f in files if stem and os.path.basename(f).split('.')[0] == stem)
            if not matches:
                if mapping.get('unmapped') != 'skip' and not (mapping.get('self') or mapping.get('by_name')):
                    receipt['reason'] = 'unmapped: ' + path
                    return result
                continue  # no test names this path: the nightly run covers it
            for rule in matches:
                for target in rule['tests']:
                    if target not in files:
                        raise ValueError('mapped test missing from inventory: ' + target)
                    chosen.add(target)
        if not chosen:
            if mapping.get('unmapped') != 'skip':
                raise ValueError('empty selection')
            result.update(setup='', test='true')
            receipt.update(mode='skip', reason='no test names the changed paths (nightly covers them)', selected=0)
            return result
        import shlex
        result['test'] = mapping['command'] + ' ' + ' '.join(shlex.quote(f) for f in sorted(chosen))
        receipt.update(mode='subset', reason='all changed paths mapped', selected=len(chosen), tests=sorted(chosen))
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as e:
        receipt['reason'] = 'mapping/diff unavailable: ' + type(e).__name__
    return result


def describe(receipt):
    if receipt['mode'] in ('changed', 'skip'):
        return f"{receipt['mode']} ({receipt['reason']})"
    count = f"{receipt['selected']}/{receipt['total']} test files" if receipt.get('total') else 'all tests'
    return f"{receipt['mode']} {count} ({receipt['reason']})"


def select_packages(d, cfg, base, head):
    """Trusted package graph: changed packages plus every transitive dependent.

    Unknown paths, missing dependencies and global configuration select full CI.
    Commands include the package's relevant checks, not only its unit tests.
    """
    import shlex
    result = dict(cfg)
    receipt = {'mode': 'full', 'reason': 'unknown package impact', 'selected': None, 'total': None}
    result['selection'] = receipt
    try:
        packages = cfg['packages']
        names = {p['name'] for p in packages}
        if len(names) != len(packages):
            return result
        for p in packages:
            if not p['path'] or not p['test'] or not set(p.get('dependencies', [])) <= names:
                return result
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=d, stderr=subprocess.PIPE).decode().strip()
        git('fetch', '-q', 'origin', base)
        ancestor = git('merge-base', base, head)
        changed = git('diff', '--name-only', '--no-renames', ancestor, head).splitlines()
        selected = set()
        for path in changed:
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in SHARED):
                return result
            owners = [p for p in packages if path.startswith(p['path'].rstrip('/') + '/')]
            if not owners:
                return result
            selected.update(p['name'] for p in owners)
        if not selected:
            return result
        while True:
            added = {p['name'] for p in packages if set(p.get('dependencies', [])) & selected}
            if added <= selected:
                break
            selected |= added
        result['test'] = ' && '.join('(cd ' + shlex.quote(p['path']) + ' && ' + p['test'] + ')'
                                    for p in packages if p['name'] in selected)
        receipt.update(mode='packages', reason='changed packages and transitive dependents',
                       packages=sorted(selected), selected=len(selected), total=len(packages))
    except (KeyError, TypeError, OSError, subprocess.SubprocessError):
        pass
    return result
