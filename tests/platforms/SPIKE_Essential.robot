*** Variables ***
${PLATFORM}      @${CURDIR}/../../platforms/boards/spike-essential.repl
${SCRIPT}        @${CURDIR}/../../scripts/single-node/spike-essential.resc

*** Test Cases ***
Essential platform is distinct and loads verified devices
    Execute Command    include ${SCRIPT}
    ${peripherals}=    Execute Command    peripherals
    Should Contain    ${peripherals}    essentialStorage
    Should Contain    ${peripherals}    imu
    Should Contain    ${peripherals}    i2c3
    Should Contain    ${peripherals}    spi2
    Should Contain    ${peripherals}    essentialPortA
    Should Contain    ${peripherals}    essentialPortB
    Should Not Contain    ${peripherals}    display
    Reset Emulation
