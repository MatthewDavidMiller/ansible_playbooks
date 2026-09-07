# Ansible Playbooks validation gates
# Usage: make [target]

.PHONY: help install lint test test-full shell clean

# Every gate runs inside the toolbox image, so rootless Podman is the only
# thing this repository needs from a workstation. scripts/toolbox.sh builds the
# image on first use and execs straight through when it is already inside one.
TOOLBOX := ./scripts/toolbox.sh
TOOLBOX_REPO := ansible-toolbox

help:
	@echo "Ansible Playbooks validation gates"
	@echo ""
	@echo "Setup:"
	@echo "  install     Build the toolbox image and install the pre-commit hook"
	@echo ""
	@echo "Quality targets:"
	@echo "  lint        ShellCheck, yamllint, ansible-lint, and playbook syntax checks"
	@echo "  test        Lint plus supply-chain, Python unit, secret-rendering,"
	@echo "              and static container policy checks (no images pulled)"
	@echo "  test-full   Everything in 'test' plus the runtime container tests,"
	@echo "              which pull the locked images and start real containers"
	@echo ""
	@echo "Dev targets:"
	@echo "  shell       Interactive shell inside the toolbox"
	@echo "  clean       Remove toolbox images and local validator caches"
	@echo ""
	@echo "Prerequisite: rootless Podman. Nothing else -- ansible-core,"
	@echo "ansible-lint, yamllint, shellcheck, and the pinned collections all"
	@echo "live in the image 'make install' builds."

# Nothing is installed onto the host: the linters, Ansible, and the pinned
# collections all live in the image. The hook path is set here too, so one
# command leaves a clone ready to commit against the full gate.
install:
	$(TOOLBOX) --build
	git config core.hooksPath hooks
	@echo "Toolbox built and pre-commit hook installed."

lint:
	$(TOOLBOX) ./scripts/lint.sh

test:
	$(TOOLBOX) ./scripts/test-local.sh

# The runtime suite is driven from here rather than from inside test-local.sh,
# because it is the one gate that has to reach the engine through its own
# command line instead of the toolbox's mounted socket. The wrapper explains
# why and picks where to run it.
test-full: test
	./scripts/run-runtime-container-tests.sh all

shell:
	$(TOOLBOX) --shell

# Toolbox images are tagged by content hash, so this removes every generation
# of them rather than one known tag. Podman qualifies a locally built image as
# localhost/<repo>, hence the anchor on either the start or a slash. Removal
# failures are ignored: an image a container still holds is collected on the
# next build instead.
clean:
	@podman info >/dev/null 2>&1 || { \
		echo "Podman is not usable here; nothing to clean."; exit 0; }; \
	podman images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
		| grep -E "(^|/)$(TOOLBOX_REPO):" \
		| xargs -r podman rmi 2>/dev/null || true
	rm -rf /tmp/ansible-playbooks-cache /tmp/ansible-playbooks-local /tmp/ansible-playbooks-remote /tmp/ansible-playbooks-trivy-cache
	find . -path ./.git -prune -o -type d -name __pycache__ -print0 | xargs -0 -r rm -rf
	@echo "Clean complete"
