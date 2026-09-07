# Model CI

The `STM32 model tests` workflow builds source only and runs the
focused STM32 DMA, SPI, and UART fixtures. It also runs the pure-Python,
transport-neutral Bluetooth H4/HCI/L2CAP/ATT/RFCOMM tests, including a loopback
TCP adapter test. It does not fetch SPIKE, LEGO, Pybricks, or TI firmware and
has no artifact-upload step. Workflow permissions are read-only.

The pinned Infrastructure fork is public and uses an HTTPS submodule URL, so
anonymous clones and pull-request CI need no repository secret or deploy key.
Checkout does not persist credentials.

The workflow runs for pushes to `main`/`feat/**` and manual dispatches. It has
read-only repository permissions and does not consume secrets.
