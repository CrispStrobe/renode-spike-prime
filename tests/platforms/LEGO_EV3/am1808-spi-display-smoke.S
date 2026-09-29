/* SPDX-License-Identifier: MIT */
/*
 * Independently authored AM1808 SPI1 -> EV3 ST7586 display proof.
 * Register layout follows TI SPRUH82C chapter 29. No LEGO code is used.
 */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000
.equ PSC1,               0x01e27000
.equ PSC_PTCMD,          0x120
.equ PSC_PTSTAT,         0x128
.equ PSC_MDSTAT10,       0x828
.equ PSC_MDCTL10,        0xa28
.equ PSC_MDSTAT3,        0x80c
.equ PSC_MDCTL3,         0xa0c
.equ PSC_STATE_MASK,     0x1f
.equ PSC_ENABLE,         0x3

.equ SYSCFG0_PINMUX5,    0x01c14134
.equ SYSCFG0_PINMUX12,   0x01c14150
.equ DISPLAY_PINMUX5,    0x00188100 /* SIMO, GP2[11], GP2[12], CLK */
.equ DISPLAY_PINMUX5_MSK,0x00ffff00
.equ DISPLAY_RESET_MUX,  0x80000000 /* GP5[0] */
.equ DISPLAY_RESET_MSK,  0xf0000000

.equ GPIO,               0x01e26000
.equ GPIO_DIR23,         0x38
.equ GPIO_SET23,         0x40
.equ GPIO_CLR23,         0x44
.equ GPIO_DIR45,         0x60
.equ GPIO_SET45,         0x68
.equ GPIO_CLR45,         0x6c
.equ LCD_A0,             0x00000800 /* GPIO43 = GP2[11] */
.equ LCD_CS,             0x00001000 /* GPIO44 = GP2[12], active low */
.equ LCD_RESET,          0x00010000 /* GPIO80 = GP5[0], active high */

.equ SPI1,               0x01f0e000
.equ SPI_GCR0,           0x00
.equ SPI_GCR1,           0x04
.equ SPI_INT0,           0x08
.equ SPI_LVL,            0x0c
.equ SPI_FLG,            0x10
.equ SPI_PC0,            0x14
.equ SPI_DAT1,           0x3c
.equ SPI_BUF,            0x40
.equ SPI_FMT0,           0x50
.equ SPI_RX_INT,         0x00000100
.equ SPI_RX_EMPTY,       0x80000000
.equ SPI_MASTER_ENABLE,  0x01000003
.equ SPI_SIMO_CLK,       0x00000600
.equ SPI_FORMAT_8BIT,    0x00000e08 /* 150 MHz / (14 + 1), MSB first, 8 bits */

.equ AINTC_GER,          0xfffee010
.equ AINTC_SICR,         0xfffee024
.equ AINTC_EISR,         0xfffee028
.equ AINTC_HIEISR,       0xfffee034
.equ AINTC_CMR14,        0xfffee438
.equ SPI1_EVENT,         56
.equ READY_MAGIC,        0x51

.section .vectors, "ax"
.global _start
_start:
    b reset
    b .
    b .
    b .
    b .
    b .
    b irq
    b .

reset:
    msr cpsr_c, #0xd2
    ldr sp, =0xffff1f00
    msr cpsr_c, #0xd3
    ldr sp, =0xffff1e00
    mov r9, #0

    /* The post-EEPROM preset leaves SPI1 clock-gated: enable PSC1 module 10. */
    ldr r0, =PSC1
    ldr r1, [r0, #PSC_MDCTL10]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_ENABLE
    str r1, [r0, #PSC_MDCTL10]
    /* The panel control lines also require the GPIO module clock. */
    ldr r1, [r0, #PSC_MDCTL3]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_ENABLE
    str r1, [r0, #PSC_MDCTL3]
    mov r1, #1
    str r1, [r0, #PSC_PTCMD]
    ldr r1, [r0, #PSC_PTSTAT]
    tst r1, #1
    bne fail_power
    ldr r1, [r0, #PSC_MDSTAT10]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail_power
    ldr r1, [r0, #PSC_MDSTAT3]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail_power

    /* SPI1 SIMO/CLK plus the three discrete display GPIO controls. */
    ldr r0, =SYSCFG0_PINMUX5
    ldr r1, [r0]
    ldr r2, =DISPLAY_PINMUX5_MSK
    bic r1, r1, r2
    ldr r2, =DISPLAY_PINMUX5
    orr r1, r1, r2
    str r1, [r0]
    ldr r1, [r0]
    ldr r2, =DISPLAY_PINMUX5_MSK
    and r1, r1, r2
    ldr r2, =DISPLAY_PINMUX5
    cmp r1, r2
    bne fail_pinmux

    ldr r0, =SYSCFG0_PINMUX12
    ldr r1, [r0]
    ldr r2, =DISPLAY_RESET_MSK
    bic r1, r1, r2
    orr r1, r1, #DISPLAY_RESET_MUX
    str r1, [r0]
    ldr r1, [r0]
    ldr r2, =DISPLAY_RESET_MSK
    and r1, r1, r2
    cmp r1, #DISPLAY_RESET_MUX
    bne fail_pinmux

    ldr r0, =GPIO
    ldr r1, [r0, #GPIO_DIR23]
    ldr r2, =LCD_A0 | LCD_CS
    bic r1, r1, r2
    str r1, [r0, #GPIO_DIR23]
    ldr r1, [r0, #GPIO_DIR45]
    ldr r2, =LCD_RESET
    bic r1, r1, r2
    str r1, [r0, #GPIO_DIR45]

    /* Inactive CS, command mode, assert then release active-high reset. */
    ldr r1, =LCD_CS
    str r1, [r0, #GPIO_SET23]
    ldr r1, =LCD_A0
    str r1, [r0, #GPIO_CLR23]
    ldr r1, =LCD_RESET
    str r1, [r0, #GPIO_SET45]
    mov r3, #64
1:
    subs r3, r3, #1
    bne 1b
    str r1, [r0, #GPIO_CLR45]

    /* Reset/release SPI1, choose functional SIMO/CLK and an 8-bit format. */
    ldr r0, =SPI1
    mov r1, #0
    str r1, [r0, #SPI_GCR0]
    mov r1, #1
    str r1, [r0, #SPI_GCR0]
    ldr r1, =SPI_SIMO_CLK
    str r1, [r0, #SPI_PC0]
    ldr r2, [r0, #SPI_PC0]
    cmp r2, r1
    bne fail_config
    ldr r1, =SPI_FORMAT_8BIT
    str r1, [r0, #SPI_FMT0]
    ldr r2, [r0, #SPI_FMT0]
    cmp r2, r1
    bne fail_config
    ldr r1, =SPI_MASTER_ENABLE
    str r1, [r0, #SPI_GCR1]
    ldr r2, [r0, #SPI_GCR1]
    cmp r2, r1
    bne fail_config

    /* Select the panel and send an independently authored one-pixel frame. */
    ldr r0, =GPIO
    ldr r1, =LCD_CS
    str r1, [r0, #GPIO_CLR23]

    mov r4, #0x11
    bl send_command
    mov r4, #0x38
    bl send_command
    mov r4, #0x3a
    bl send_command
    mov r4, #0x02
    bl send_data
    mov r4, #0x20
    bl send_command
    mov r4, #0x29
    bl send_command
    mov r4, #0x2a
    bl send_command
    mov r4, #0
    bl send_data
    bl send_data
    bl send_data
    bl send_data
    mov r4, #0x2b
    bl send_command
    mov r4, #0
    bl send_data
    bl send_data
    bl send_data
    bl send_data
    mov r4, #0x2c
    bl send_command
    mov r4, #0xe0
    bl send_data

    /* Route SPI1 RX completion through physical AINTC event 56. */
    ldr r0, =AINTC_CMR14
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #SPI1_EVENT
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]
    ldr r0, =SPI1
    ldr r1, =SPI_RX_INT
    str r1, [r0, #SPI_LVL]
    str r1, [r0, #SPI_INT0]
    mov r9, #READY_MAGIC
    msr cpsr_c, #0x53

    /* A final display-on command supplies mutation-sensitive RX IRQ evidence. */
    ldr r0, =GPIO
    ldr r1, =LCD_A0
    str r1, [r0, #GPIO_CLR23]
    ldr r0, =SPI1
    mov r1, #0x29
    str r1, [r0, #SPI_DAT1]
2:
    b 2b

/* r4 byte; each non-final transfer drains RX to avoid hiding overruns. */
send_command:
    ldr r0, =GPIO
    ldr r1, =LCD_A0
    str r1, [r0, #GPIO_CLR23]
    b send_byte

send_data:
    ldr r0, =GPIO
    ldr r1, =LCD_A0
    str r1, [r0, #GPIO_SET23]

send_byte:
    ldr r0, =SPI1
    str r4, [r0, #SPI_DAT1]
    ldr r3, =0x00010000
3:
    ldr r1, [r0, #SPI_FLG]
    tst r1, #SPI_RX_INT
    bne 4f
    subs r3, r3, #1
    bne 3b
    b fail_transfer
4:
    ldr r1, [r0, #SPI_BUF]
    tst r1, #SPI_RX_EMPTY
    bne fail_transfer
    movs r2, r1, lsl #16
    bne fail_transfer
    bx lr

irq:
    stmfd sp!, {r0-r3, lr}
    cmp r9, #READY_MAGIC
    bne fail_irq_from_exception
    ldr r0, =SPI1
    ldr r1, [r0, #SPI_FLG]
    tst r1, #SPI_RX_INT
    beq fail_irq_from_exception
    ldr r1, [r0, #SPI_BUF]
    tst r1, #SPI_RX_EMPTY
    bne fail_irq_from_exception
    movs r2, r1, lsl #16
    bne fail_irq_from_exception
    ldr r0, =GPIO
    ldr r1, =LCD_CS
    str r1, [r0, #GPIO_SET23]
    ldr r0, =AINTC_SICR
    mov r1, #SPI1_EVENT
    str r1, [r0]
    ldr r1, =success_message
    b print_from_exception

fail_power:
    ldr r1, =failure_power_message
    b print
fail_pinmux:
    ldr r1, =failure_pinmux_message
    b print
fail_transfer:
    ldr r1, =failure_transfer_message
    b print
fail_config:
    ldr r1, =failure_config_message
    b print
fail_irq_from_exception:
    ldr r1, =failure_irq_message
print_from_exception:
    /* Terminal proof path: do not restore r1 and lose the selected message. */
    b print
print:
    ldr r0, =UART1_THR
5:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 6f
    strb r2, [r0]
    b 5b
6:
    b 6b

success_message:
    .asciz "EV3 SPI DISPLAY IRQ OK\n"
failure_power_message:
    .asciz "EV3 SPI DISPLAY FAIL POWER\n"
failure_pinmux_message:
    .asciz "EV3 SPI DISPLAY FAIL PINMUX\n"
failure_transfer_message:
    .asciz "EV3 SPI DISPLAY FAIL TRANSFER\n"
failure_config_message:
    .asciz "EV3 SPI DISPLAY FAIL CONFIG\n"
failure_irq_message:
    .asciz "EV3 SPI DISPLAY FAIL IRQ\n"
