/* SPDX-License-Identifier: MIT */
/*
 * Independently authored EV3 GPIO -> AINTC -> ARM926 executable proof.
 * Register layout follows TI SPRUH82C chapter 20. No LEGO code is used.
 */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000
.equ PSC1,               0x01e27000
.equ PSC_PTCMD,          0x120
.equ PSC_PTSTAT,         0x128
.equ PSC_MDSTAT3,        0x80c
.equ PSC_MDCTL3,         0xa0c
.equ PSC_STATE_MASK,     0x1f
.equ PSC_ENABLE,         0x3

.equ SYSCFG0_PINMUX2,    0x01c14128
.equ SYSCFG0_PINMUX14,   0x01c14158
.equ PINMUX2_GP1_13,     0x00000400
.equ PINMUX2_GP1_13_MSK, 0x00000f00
.equ PINMUX14_GP6_7,     0x00000008
.equ PINMUX14_GP6_7_MSK, 0x0000000f

.equ GPIO,               0x01e26000
.equ GPIO_BINTEN,        0x08
.equ GPIO_DIR01,         0x10
.equ GPIO_IN01,          0x20
.equ GPIO_SET_RIS01,     0x24
.equ GPIO_CLR_FAL01,     0x30
.equ GPIO_INTSTAT01,     0x34
.equ GPIO_DIR67,         0x88
.equ GPIO_OUT67,         0x8c
.equ GPIO_SET67,         0x90
.equ GPIO_CLR67,         0x94
.equ CENTER_BUTTON,      0x20000000 /* GPIO29 = GP1[13], pair bit 29 */
.equ STATUS_LED,         0x00000080 /* GPIO103 = GP6[7], pair bit 7 */
.equ BANK1_ENABLE,       0x00000002

.equ AINTC_GER,          0xfffee010
.equ AINTC_SICR,         0xfffee024
.equ AINTC_EISR,         0xfffee028
.equ AINTC_HIEISR,       0xfffee034
.equ AINTC_CMR10,        0xfffee428
.equ GPIO_BANK1_EVENT,   43

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

    /* The post-EEPROM preset leaves GPIO clock-gated: enable PSC1 module 3. */
    ldr r0, =PSC1
    ldr r1, [r0, #PSC_MDCTL3]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_ENABLE
    str r1, [r0, #PSC_MDCTL3]
    mov r1, #1
    str r1, [r0, #PSC_PTCMD]
    ldr r1, [r0, #PSC_PTSTAT]
    tst r1, #1
    bne fail_power
    ldr r1, [r0, #PSC_MDSTAT3]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail_power

    /* Select GPIO functions for the center button and one status LED. */
    ldr r0, =SYSCFG0_PINMUX2
    ldr r1, [r0]
    bic r1, r1, #PINMUX2_GP1_13_MSK
    orr r1, r1, #PINMUX2_GP1_13
    str r1, [r0]
    ldr r2, [r0]
    and r2, r2, #PINMUX2_GP1_13_MSK
    cmp r2, #PINMUX2_GP1_13
    bne fail_pinmux

    ldr r0, =SYSCFG0_PINMUX14
    ldr r1, [r0]
    bic r1, r1, #PINMUX14_GP6_7_MSK
    orr r1, r1, #PINMUX14_GP6_7
    str r1, [r0]
    ldr r2, [r0]
    and r2, r2, #PINMUX14_GP6_7_MSK
    cmp r2, #PINMUX14_GP6_7
    bne fail_pinmux

    ldr r0, =GPIO

    /* GP6[7] is an output. Prove independent SET and CLR paths/readback. */
    ldr r1, [r0, #GPIO_DIR67]
    bic r1, r1, #STATUS_LED
    str r1, [r0, #GPIO_DIR67]
    ldr r1, =STATUS_LED
    str r1, [r0, #GPIO_SET67]
    ldr r2, [r0, #GPIO_OUT67]
    tst r2, r1
    beq fail_output
    str r1, [r0, #GPIO_CLR67]
    ldr r2, [r0, #GPIO_OUT67]
    tst r2, r1
    bne fail_output
    str r1, [r0, #GPIO_SET67]

    /* GP1[13] is an input with rising-only edge detection. */
    ldr r1, [r0, #GPIO_DIR01]
    ldr r2, =CENTER_BUTTON
    orr r1, r1, r2
    str r1, [r0, #GPIO_DIR01]
    str r2, [r0, #GPIO_SET_RIS01]
    str r2, [r0, #GPIO_CLR_FAL01]
    ldr r1, =BANK1_ENABLE
    str r1, [r0, #GPIO_BINTEN]

    /* Event 43 occupies CMR10 byte 3; host channel 1 is IRQ. */
    ldr r0, =AINTC_CMR10
    ldr r1, =0x01000000
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #GPIO_BANK1_EVENT
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]
    msr cpsr_c, #0x53
    ldr r8, =0x00100000

wait_for_button:
    add r6, r6, #1
    eor r7, r7, r6, ror #7
    subs r8, r8, #1
    beq fail_timeout
    b wait_for_button

irq:
    stmfd sp!, {r0-r3, lr}
    ldr r0, =GPIO
    ldr r1, [r0, #GPIO_INTSTAT01]
    ldr r2, =CENTER_BUTTON
    tst r1, r2
    beq fail_irq_from_exception
    ldr r1, [r0, #GPIO_IN01]
    tst r1, r2
    beq fail_input_from_exception
    str r2, [r0, #GPIO_INTSTAT01]
    ldr r0, =AINTC_SICR
    mov r1, #GPIO_BANK1_EVENT
    str r1, [r0]
    ldr r1, =success_message
    b print_from_exception

fail_power:
    ldr r1, =failure_power_message
    b print
fail_pinmux:
    ldr r1, =failure_pinmux_message
    b print
fail_output:
    ldr r1, =failure_output_message
    b print
fail_timeout:
    ldr r1, =failure_timeout_message
    b print
fail_irq_from_exception:
    ldr r1, =failure_irq_message
    b print_from_exception
fail_input_from_exception:
    ldr r1, =failure_input_message

print_from_exception:
    /* Terminal proof path: do not restore r1 and lose the selected message. */
    b print
print:
    ldr r0, =UART1_THR
1:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 2f
    strb r2, [r0]
    b 1b
2:
    b 2b

success_message:
    .asciz "EV3 GPIO BUTTON LED OK\n"
failure_power_message:
    .asciz "EV3 GPIO FAIL POWER\n"
failure_pinmux_message:
    .asciz "EV3 GPIO FAIL PINMUX\n"
failure_output_message:
    .asciz "EV3 GPIO FAIL OUTPUT\n"
failure_timeout_message:
    .asciz "EV3 GPIO FAIL TIMEOUT\n"
failure_irq_message:
    .asciz "EV3 GPIO FAIL IRQ\n"
failure_input_message:
    .asciz "EV3 GPIO FAIL INPUT\n"
