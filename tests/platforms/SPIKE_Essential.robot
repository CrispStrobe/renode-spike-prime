*** Variables ***
${PLATFORM}      @${CURDIR}/../../platforms/boards/spike-essential.repl

*** Test Cases ***
Essential platform is distinct and loads verified devices
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}
    ${peripherals}=    Execute Command    peripherals
    Should Contain    ${peripherals}    essentialStorage
    Should Contain    ${peripherals}    imu
    Should Contain    ${peripherals}    i2c3
    Should Contain    ${peripherals}    fmpi2c1
    Should Contain    ${peripherals}    essentialLeds
    Should Contain    ${peripherals}    spi2
    Should Not Contain    ${peripherals}    display
    Reset Emulation
