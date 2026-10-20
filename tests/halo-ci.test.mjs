import { test } from 'node:test'
import { execFileSync } from 'node:child_process'
test('HALO PR head and train contracts',()=>execFileSync('python3',['-B','tests/halo-ci.test.py'],{stdio:'pipe'}))
