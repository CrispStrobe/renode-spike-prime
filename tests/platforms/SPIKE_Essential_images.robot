*** Variables ***
${IMAGE_ROOT}    ${CURDIR}/../../.local/spike-essential-images
${PLATFORM}      @${CURDIR}/../../platforms/boards/spike-essential.repl

*** Test Cases ***
User supplied official Essential image has valid vectors and progresses
    Create Essential Machine
    Verify Local Image And Progress    official
    Reset Emulation

User supplied Pybricks Essential image has valid vectors and progresses
    Create Essential Machine
    Verify Local Image And Progress    pybricks
    Reset Emulation

*** Keywords ***
Create Essential Machine
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}

Verify Local Image And Progress
    [Arguments]    ${kind}
    ${present}=    Run Keyword And Return Status    File Should Exist    ${IMAGE_ROOT}/${kind}/manifest.json
    Skip If    not ${present}    No user-supplied ${kind} Essential image manifest
    ${manifest_text}=    Get File    ${IMAGE_ROOT}/${kind}/manifest.json
    ${manifest}=    Evaluate    json.loads($manifest_text)    json
    ${image}=    Set Variable    ${IMAGE_ROOT}/${kind}/image.${manifest}[format]
    File Should Exist    ${image}
    ${actual_hash}=    Evaluate    hashlib.sha256(open(r'''${image}''', 'rb').read()).hexdigest()    hashlib
    Should Be Equal    ${manifest}[sha256]    ${actual_hash}
    IF    '${manifest}[format]' == 'elf'
        Execute Command    sysbus LoadELF @${image}
    ELSE
        Execute Command    sysbus LoadBinary @${image} ${manifest}[load_address]
        Execute Command    cpu VectorTableOffset ${manifest}[load_address]
    END
    ${vector_base}=    Set Variable    ${manifest}[load_address]
    ${initial_sp}=    Execute Command    sysbus ReadDoubleWord ${vector_base}
    ${reset_vector}=    Evaluate    int($vector_base, 0) + 4
    ${initial_pc}=    Execute Command    sysbus ReadDoubleWord ${reset_vector}
    ${sp}=    Convert To Integer    ${initial_sp.strip()}
    ${pc}=    Evaluate    int($initial_pc.strip(), 0) & ~1
    Should Be True    0x20000000 <= ${sp} < 0x20050000
    Should Be True    0x08000000 <= ${pc} < 0x08100000
    Execute Command    cpu SP ${sp}
    Execute Command    cpu PC ${pc}
    Execute Command    cpu Step 1000
    ${after}=    Execute Command    cpu GetRegister "PC"
    Should Not Be Equal As Numbers    ${pc}    ${after.strip()}
