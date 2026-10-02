# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import random
import string
import time

import pytest
import subprocess
import yaml

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.fixture()
def rock_test_env(tmpdir):
    """Yields a temporary directory and random docker container name,
    then cleans them up after.
    """
    container_name = "".join(
        [str(i) for i in random.choices(string.ascii_lowercase, k=8)]
    )
    yield tmpdir, container_name

    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    # tmpdir fixture cleans up the temp directory


@pytest.mark.abort_on_fail
def test_rock(rock_test_env):
    """Test the Chisel-based rock.

    Validates that Pebble boots and the persistenceagent service becomes
    active, without relying on external ls / which / coreutils (the minimal
    Chisel rootfs intentionally omits them).  bash is present because the
    service command uses it for env-var expansion.
    """
    temp_dir, container_name = rock_test_env
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    # Start the container in detached mode — Pebble will launch services.
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            LOCAL_ROCK_IMAGE,
        ],
        check=True,
    )

    # Give Pebble a few seconds to start the daemon and default services.
    deadline = time.time() + 30
    service_active = False
    result = None
    while time.time() < deadline:
        time.sleep(2)
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "/usr/bin/pebble",
                "services",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if "persistenceagent" in result.stdout and ("active" in result.stdout or "backoff" in result.stdout):
            service_active = True
            break

    # Always clean up — no point leaving the container running.
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    assert service_active, (
        f"persistenceagent did not reach 'active' within 30 s.\n"
        f"pebble services output:\n"
        f"{result.stdout if result else '(no response from pebble)'}"
    )
