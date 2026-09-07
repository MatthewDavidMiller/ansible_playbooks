# The validation toolbox: every linter, test runner, and collection this
# repository's gates depend on, so a workstation needs nothing from the host
# but rootless Podman. scripts/toolbox.sh builds this image and runs the
# gates inside it.
#
# The base is the digest-pinned Alpine image the local validation scripts
# already use. scripts/toolbox.sh reads it out of artifacts/test_images.lock.yml
# and passes it in as ALPINE_REF; there is deliberately no default here, because
# the lock file is the one place this repository records that digest and a
# default would be a second one free to drift from it. Bumping the base is
# therefore the same reviewed lock-file change as any other image bump.
#
# This image is a developer tool, not a deployed artifact: it is never pushed,
# never serves traffic, and only ever runs this repository's own gates.
#
# It declares no USER on purpose. scripts/toolbox.sh supplies the uid at run
# time -- the invoking user's, so a gate leaves no root-owned files in the
# working tree -- and that uid is not known when the image is built. Baking one
# in would collide with the --userns=keep-id mapping that puts it there.

ARG ALPINE_REF
FROM ${ALPINE_REF}

SHELL ["/bin/ash", "-eo", "pipefail", "-c"]

# coreutils, findutils, grep, sed, gawk, and diffutils replace busybox's
# applets with the GNU ones the gates are written against: the scripts use
# GNU-only behaviour throughout, and busybox's `sed -E`, `grep -r --include`,
# and `mktemp` differ enough to change results silently rather than fail.
#
# bash is what every gate script and the pre-commit hook declare; Alpine ships
# only ash by default.
#
# git is not just for reading history: ansible-lint discovers the files it
# lints through it, and hooks/pre-commit selects YAML files with `git ls-files`.
#
# podman-remote talks to the host engine through the API socket
# scripts/toolbox.sh mounts and points CONTAINER_HOST at. There is no engine in
# here: it is a client, and the pinned skopeo/cosign/trivy containers that
# scripts/promote_artifacts.py falls back to run on the host. It is installed
# under the name every caller uses, which is why the symlink follows.
#
# The runtime container tests deliberately do not go through it: they set up
# and hand back fixture directories with `podman unshare`, which the remote
# client refuses because a user namespace is local to the machine holding the
# files. See scripts/run-runtime-container-tests.sh.
#
# ripgrep is not a convenience here: scripts/test_supply_chain_policy.sh asserts
# every one of its policies through `rg`, and relies on its `--glob` exclusions
# to keep the assertion patterns from matching the script that declares them.
#
# build-base, python3-dev, libffi-dev, and openssl-dev are a fallback for the
# ansible-lint dependency tree. cffi, cryptography, PyYAML, and
# ruamel.yaml.clib all publish musllinux wheels, so the install below normally
# compiles nothing; these keep a wheel-less release from turning into a broken
# image build.
RUN apk add --no-cache \
        bash \
        build-base \
        coreutils \
        curl \
        diffutils \
        file \
        findutils \
        gawk \
        git \
        grep \
        libffi-dev \
        openssl-dev \
        podman-remote \
        py3-pip \
        python3 \
        python3-dev \
        ripgrep \
        sed \
        shellcheck \
        tar \
        xz \
    && ln -s podman-remote /usr/bin/podman

# Alpine marks its Python installation externally managed, so the tooling lives
# in a virtualenv exactly as it would on a host -- baked into the image rather
# than into the mounted tree, so a gate run never writes a venv into the
# working copy.
COPY tests/requirements-dev.txt /tmp/requirements-dev.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && rm /tmp/requirements-dev.txt

# The pinned collections, installed from the same manifest a control node uses.
# /usr/share/ansible/collections is already the second entry in ansible.cfg's
# collections_path, so the playbooks resolve them here without the gates having
# to populate the git-ignored collections/ansible_collections/ in the tree.
COPY collections/requirements.yml /tmp/collections-requirements.yml
RUN /opt/venv/bin/ansible-galaxy collection install \
        -r /tmp/collections-requirements.yml \
        -p /usr/share/ansible/collections \
    && rm /tmp/collections-requirements.yml

ENV PATH="/opt/venv/bin:${PATH}"

# scripts/toolbox.sh runs a command directly when it sees this rather than
# starting another container. The gates chain into each other -- the pre-commit
# hook runs test-local.sh, which runs lint.sh -- and each entry point routes
# through the toolbox, so without this a single commit would nest containers
# several deep.
ENV ANSIBLE_PLAYBOOKS_IN_TOOLBOX=1

# Ansible and ansible-lint both want a writable HOME for caches and temporary
# files. The container runs as whichever uid invoked it, so this is
# world-writable with the sticky bit, the same treatment /tmp gets.
ENV HOME=/home/toolbox
ENV XDG_CACHE_HOME=/home/toolbox/.cache
ENV ANSIBLE_LOCAL_TEMP=/home/toolbox/.ansible/tmp
ENV ANSIBLE_REMOTE_TEMP=/home/toolbox/.ansible/tmp

# The bind-mounted repository looks foreign-owned to git whenever the mapped
# uid does not match, which is the ordinary case under rootless Podman.
RUN mkdir -p /home/toolbox \
    && chmod 1777 /home/toolbox \
    && git config --system --add safe.directory '*'

# A placeholder only: scripts/toolbox.sh sets the working directory to the
# repository's own absolute path.
WORKDIR /work
