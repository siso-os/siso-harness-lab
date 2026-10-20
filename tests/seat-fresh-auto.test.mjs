import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
test('automatic refresh guards, launch recovery and archive ordering', () => {
  execFileSync('python3', ['-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_seat_fresh_auto.py'], { stdio: 'pipe' });
});
