*** Settings ***
Library          OperatingSystem
Library          Process
Test Teardown    Reset Scenario
Test Timeout     120 seconds

*** Variables ***
${IMAGE_ROOT}    %{SPIKE_FIRMWARE_IMAGE_ROOT=${CURDIR}/../../.local/spike-firmware-scenarios}
${TOOL}          ${CURDIR}/../../tools/spike-firmware-scenarios/scenario_manifest.py
${STATE_PORT}    0
${OPAQUE_INSTRUCTION_BUDGET}    2000
${PROTECTED_INSTRUCTION_CEILING}    100000000

*** Test Cases ***
LEGO Prime v2 unchanged image progresses
    Run Opaque Scenario    lego-prime-v2

LEGO Prime v3 unchanged image progresses
    Run Opaque Scenario    lego-prime-v3

Pybricks Prime unchanged image progresses
    Run Opaque Scenario    pybricks-prime

spike-nx unchanged protected image reaches boot boundaries
    Run Protected Scenario    spike-nx    ${False}

Brickwright NuttX Renode profile reaches daemon and state boundaries
    Run Protected Scenario    brickwright-nuttx    ${True}

LEGO Essential unchanged image progresses
    Run Opaque Scenario    lego-essential

Pybricks Essential unchanged image progresses
    Run Opaque Scenario    pybricks-essential

*** Keywords ***
Verify Before Creating Machine
    [Arguments]    ${target}
    ${check}=    Run Process    python3    ${TOOL}    --root    ${IMAGE_ROOT}    verify    ${target}    --execution-json
    IF    ${check.rc} == 77
        Skip    ${check.stdout}
    END
    Should Be Equal As Integers    ${check.rc}    0    Hash preflight failed: ${check.stderr}
    ${input}=    Evaluate    json.loads($check.stdout)    json
    RETURN    ${input}

Create Target Machine
    [Arguments]    ${board}
    Execute Command    mach create
    IF    '${board}' == 'prime'
        Execute Command    machine LoadPlatformDescription @${CURDIR}/../../platforms/boards/spike-prime.repl
    ELSE
        Execute Command    machine LoadPlatformDescription @${CURDIR}/../../platforms/boards/spike-essential-brick-devices.repl
    END

Load Artifact
    [Arguments]    ${target}    ${artifact}
    ${path}=    Set Variable    ${IMAGE_ROOT}/${target}/${artifact}[file]
    IF    '${artifact}[format]' == 'elf'
        Execute Command    sysbus LoadELF @${path}
    ELSE
        Execute Command    sysbus LoadBinary @${path} ${artifact}[load_address]
    END

Set And Validate Vectors
    [Arguments]    ${base}
    Execute Command    cpu VectorTableOffset ${base}
    ${initial_sp_text}=    Execute Command    sysbus ReadDoubleWord ${base}
    ${reset_address}=    Evaluate    int($base, 0) + 4
    ${initial_pc_text}=    Execute Command    sysbus ReadDoubleWord ${reset_address}
    ${initial_sp}=    Convert To Integer    ${initial_sp_text.strip()}
    ${initial_pc}=    Evaluate    int($initial_pc_text.strip(), 0) & ~1
    Should Be True    0x20000000 <= ${initial_sp} <= 0x20050000
    Should Be True    0x08000000 <= ${initial_pc} < 0x08200000
    Execute Command    cpu SP ${initial_sp}
    Execute Command    cpu PC ${initial_pc}
    RETURN    ${initial_pc}

Run Opaque Scenario
    [Arguments]    ${target}
    ${input}=    Verify Before Creating Machine    ${target}
    Create Target Machine    ${input}[board]
    Load Artifact    ${target}    ${input}[artifacts][0]
    ${pc}=    Set And Validate Vectors    ${input}[artifacts][0][load_address]
    Execute Command    cpu Step ${OPAQUE_INSTRUCTION_BUDGET}
    ${after_text}=    Execute Command    cpu GetRegister "PC"
    ${after}=    Convert To Integer    ${after_text.strip()}
    Should Not Be Equal As Numbers    ${pc}    ${after}
    Should Be True    0x08000000 <= ${after} < 0x08200000

Run Protected Scenario
    [Arguments]    ${target}    ${with_h4}
    ${input}=    Verify Before Creating Machine    ${target}
    Create Target Machine    ${input}[board]
    Load Artifact    ${target}    ${input}[artifacts][0]
    Load Artifact    ${target}    ${input}[artifacts][1]
    ${pc}=    Set And Validate Vectors    ${input}[artifacts][0][load_address]
    ${nx_start}=    Execute Command    sysbus GetSymbolAddress "nx_start"
    ${board_late}=    Execute Command    sysbus GetSymbolAddress "board_late_initialize"
    ${bringup}=    Execute Command    sysbus GetSymbolAddress "stm32_bringup"
    Create Log Tester    1
    Execute Command    cpu AddHook ${nx_start.strip()} "monitor.Parse('log \\"MILESTONE nx_start\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${board_late.strip()} "monitor.Parse('log \\"MILESTONE board_late_initialize\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${bringup.strip()} "monitor.Parse('log \\"MILESTONE stm32_bringup\\"'); machine.PauseAndRequestEmulationPause()"
    IF    $with_h4
        Set Up Brickwright Simulation Hooks
    END
    Start Emulation
    Wait For Log Entry    MILESTONE nx_start    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE board_late_initialize    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE stm32_bringup    timeout=10
    IF    $with_h4
        Start Emulation
        Wait For Log Entry    MILESTONE imu_init    timeout=10
        Start Emulation
        Wait For Log Entry    MILESTONE storage_init    timeout=10
        Start Emulation
        Wait For Log Entry    MILESTONE display_init    timeout=15
        Start Emulation
        Wait For Log Entry    MILESTONE bluetooth_board_init    timeout=10
        Start Emulation
        Wait For Log Entry    MILESTONE daemon_ready    timeout=30
        Assert Brickwright State Snapshot
    END
    Assert Protected Instruction Ceiling

Assert Protected Instruction Ceiling
    ${instructions_text}=    Execute Command    cpu ExecutedInstructions
    ${instructions}=    Convert To Integer    ${instructions_text.strip()}
    Should Be True    0 < ${instructions} <= ${PROTECTED_INSTRUCTION_CEILING}

Set Up Brickwright Simulation Hooks
    Execute Command    include "${CURDIR}/../../scripts/spike-state-server.py"
    Execute Command    spike_state_start "127.0.0.1" ${STATE_PORT} "${CURDIR}/../../contracts/brick-state/renode-prime.example.json"
    ${state_port_text}=    Execute Command    spike_state_port
    ${state_port}=    Convert To Integer    ${state_port_text.strip()}
    Set Test Variable    ${STATE_PORT}    ${state_port}
    ${imu}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${storage}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    ${bluetooth}=    Execute Command    sysbus GetSymbolAddress "stm32_bluetooth_initialize"
    ${ready}=    Execute Command    sysbus GetSymbolAddress "brickwright_simulation_daemon_ready"
    Execute Command    cpu AddHook ${imu.strip()} "monitor.Parse('log \\"MILESTONE imu_init\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${storage.strip()} "monitor.Parse('log \\"MILESTONE storage_init\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${display.strip()} "monitor.Parse('log \\"MILESTONE display_init\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${bluetooth.strip()} "monitor.Parse('log \\"MILESTONE bluetooth_board_init\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${ready.strip()} "monitor.Parse('log \\"MILESTONE daemon_ready\\"'); machine.PauseAndRequestEmulationPause()"

Assert Brickwright State Snapshot
    ${read}=    Run Process    python3    ${CURDIR}/../../tools/spike-state-read-once.py    127.0.0.1    ${STATE_PORT}    --board    spike-prime    --firmware    brickwright-nuttx
    ${server_error}=    Execute Command    spike_state_error
    Should Be Equal As Integers    ${read.rc}    0    State snapshot failed: ${read.stderr}; server: ${server_error}
    ${snapshot}=    Evaluate    json.loads($read.stdout)    json
    Should Be Equal    ${snapshot}[type]    snapshot
    Should Be Equal    ${snapshot}[target][board]    spike-prime
    Should Be Equal    ${snapshot}[target][firmware]    brickwright-nuttx
    Should Be Equal As Integers    ${snapshot}[display][width]    5
    Should Be Equal As Integers    ${snapshot}[display][height]    5
    Should Be True    ${snapshot}[battery][millivolts] >= 0

Reset Scenario
    Terminate All Processes    kill=True
    Run Keyword And Ignore Error    Execute Command    spike_state_stop
    Reset Emulation
