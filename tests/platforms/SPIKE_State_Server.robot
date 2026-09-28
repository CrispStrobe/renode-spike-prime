*** Test Cases ***
Should Load And Start Monitor State Service
    Execute Command    mach create
    Execute Command    include "${CURDIR}/../../scripts/spike-state-server.py"
    Execute Command    spike_state_start "127.0.0.1" 0 "${CURDIR}/../../contracts/brick-state/renode-prime.example.json"
    Execute Command    spike_state_stop
