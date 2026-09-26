from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which('bash')


@pytest.mark.skipif(BASH is None, reason='Bash integration tests run in Linux CI')
@pytest.mark.parametrize('needs_sudo', ['false', 'true'])
def test_napcat_image_override_survives_sudo_environment_filtering(
    tmp_path: Path, needs_sudo: str
) -> None:
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(REPOSITORY_ROOT / 'scripts/lib.sh', scripts / 'lib.sh')
    (tmp_path / 'docker-compose.yml').write_text('services: {}\n', encoding='utf-8')
    target = 'mlikiowa/napcat-docker:v1.2.3@sha256:' + '0' * 64
    shell = r'''
set -euo pipefail
needs_sudo=$1
target=$2
project=$3
docker() {
  if [[ "$1" == info ]]; then
    [[ "$needs_sudo" == false || "${under_sudo:-false}" == true ]]
    return
  fi
  # Read the last Compose -f file, as Docker does for an image override.
  local previous='' override=''
  for arg in "$@"; do
    if [[ "$previous" == '-f' ]]; then override=$arg; fi
    previous=$arg
  done
  test -f "$override"
  grep -F "image: \"$target\"" "$override"
}
sudo() {
  # Model sudo's default removal of an inline NAPCAT_IMAGE assignment.
  unset NAPCAT_IMAGE
  under_sudo=true "$@"
}
source "$project/scripts/lib.sh"
compose_with_napcat_image "$target" up -d --no-deps napcat
'''
    result = subprocess.run(
        [BASH, '-c', shell, 'test', needs_sudo, target, tmp_path.as_posix()],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert target in result.stdout
    assert list(tmp_path.glob('.compose-napcat.*.yaml')) == []


@pytest.mark.skipif(BASH is None, reason='Bash integration tests run in Linux CI')
def test_napcat_image_override_rejects_unpinned_targets(tmp_path: Path) -> None:
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(REPOSITORY_ROOT / 'scripts/lib.sh', scripts / 'lib.sh')
    shell = r'''
set -euo pipefail
docker() { [[ "$1" == info ]]; }
source "$1/scripts/lib.sh"
compose_with_napcat_image 'mlikiowa/napcat-docker:latest' up -d napcat
'''
    result = subprocess.run(
        [BASH, '-c', shell, 'test', tmp_path.as_posix()],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert list(tmp_path.glob('.compose-napcat.*.yaml')) == []


@pytest.mark.skipif(BASH is None, reason='Bash integration tests run in Linux CI')
def test_ai_setup_preserves_literal_provider_values(tmp_path: Path) -> None:
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(REPOSITORY_ROOT / 'scripts/set-ai-config.sh', scripts / 'set-ai-config.sh')
    environment = tmp_path / '.env'
    environment.write_text(
        'AI_ENABLED=false\nAI_API_KEY=\nAI_BASE_URL=\nAI_MODEL=\n', encoding='utf-8'
    )
    base_url = 'https://example.invalid/v1?name=$VALUE#part'
    model = "team's model $VALUE"
    credential = "test-dollar-$VALUE-backslash-\\-apostrophe-'-hash-#"
    result = subprocess.run(
        [BASH, (scripts / 'set-ai-config.sh').as_posix()],
        input=('\n'.join([base_url, model, 'all', 'mention', credential]) + '\n').encode(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    values = dotenv_values(environment, interpolate=False)
    assert values['AI_API_KEY'] == credential
    assert values['AI_BASE_URL'] == base_url
    assert values['AI_MODEL'] == model
    assert credential.encode() not in result.stdout + result.stderr
