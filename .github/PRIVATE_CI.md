# Private model CI

The `Private STM32 model tests` workflow builds source only and runs the
focused STM32 DMA, SPI, and UART fixtures. It does not fetch SPIKE, LEGO, Pybricks, or TI
firmware and has no artifact-upload step. Workflow permissions are read-only.

GitHub scopes the automatic `GITHUB_TOKEN` to this top-level private
repository, so it cannot clone the separate private Infrastructure submodule.
The repository is configured with:

- a read-only deploy key on `CrispStrobe/renode-infrastructure-spike-prime`;
- its private half as the top-level repository secret
  `RENODE_INFRASTRUCTURE_DEPLOY_KEY`.

The key grants access only to that one Infrastructure repository and cannot
write to it. The workflow fails before checkout with a specific error when the
secret is absent. Checkout does not persist credentials.

The workflow intentionally runs only for pushes to `main`/`feat/**` and manual
dispatches in the private repository. It does not run on pull requests, where
secrets may be withheld or untrusted code could otherwise receive the token.
