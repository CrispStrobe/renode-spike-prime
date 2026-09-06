# Private model CI

The `Private STM32 model tests` workflow builds source only and runs the
focused `STM32DMATests` fixture. It does not fetch SPIKE, LEGO, Pybricks, or TI
firmware and has no artifact-upload step. Workflow permissions are read-only.

GitHub scopes the automatic `GITHUB_TOKEN` to this top-level private
repository, so it cannot clone the separate private Infrastructure submodule.
Configure this repository secret:

- `RENODE_INFRASTRUCTURE_TOKEN`: a fine-grained personal access token limited
  to the `CrispStrobe/renode-spike-prime` and
  `CrispStrobe/renode-infrastructure-spike-prime` repositories, with only
  read-only **Contents** permission.

The token must not have write, administration, workflow, package, or other
repository permissions. The workflow fails before checkout with a specific
error when the secret is absent. Checkout does not persist credentials.

The workflow intentionally runs only for pushes to `main`/`feat/**` and manual
dispatches in the private repository. It does not run on pull requests, where
secrets may be withheld or untrusted code could otherwise receive the token.
