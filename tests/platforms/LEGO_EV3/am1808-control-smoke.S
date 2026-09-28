/* SPDX-License-Identifier: MIT */
/*
 * Independently authored AM1808 PSC/PLLC/SYSCFG executable proof.
 * Register addresses and sequences follow TI SPRUH82C chapters 7, 8 and 10.
 * This source contains no LEGO firmware material.
 */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000

.equ PSC0_BASE,          0x01c10000
.equ PSC_PTCMD,          0x120
.equ PSC_PTSTAT,         0x128
.equ PSC_MDSTAT6,        0x818
.equ PSC_MDCTL6,         0xa18
.equ PSC_STATE_MASK,     0x1f
.equ PSC_SYNCRESET,      0x1
.equ PSC_ENABLE,         0x3

.equ PLL0_BASE,          0x01c11000
.equ PLL_PLLM,           0x110
.equ PLL_PREDIV,         0x114
.equ PLL_DIV2,           0x11c
.equ PLL_POSTDIV,        0x128
.equ PLL_CMD,            0x138
.equ PLL_STAT,           0x13c
.equ PLL_DIV6,           0x168

.equ SYSCFG0_BASE,       0x01c14000
.equ SYSCFG_KICK0,       0x38
.equ SYSCFG_KICK1,       0x3c
.equ SYSCFG_PINMUX3,     0x12c
.equ SYSCFG_PINMUX4,     0x130
.equ SYSCFG_PINMUX10,    0x148
.equ SYSCFG_SUSPSRC,     0x170
.equ SYSCFG_CFGCHIP2,    0x184
.equ KICK0_KEY,          0x83e70b13
.equ KICK1_KEY,          0x95a4f1e0

.section .vectors, "ax"
.global _start
_start:
    b reset
    b .
    b .
    b .
    b .
    b .
    b .
    b .

reset:
    msr cpsr_c, #0xd3
    ldr sp, =0xffff1e00

    /* Validate the explicit post-EEPROM PLL0 handoff state. */
    ldr r0, =PLL0_BASE
    ldr r1, [r0, #PLL_PLLM]
    cmp r1, #0x18
    bne fail
    ldr r1, [r0, #PLL_PREDIV]
    ldr r2, =0x8000
    cmp r1, r2
    bne fail
    ldr r1, [r0, #PLL_POSTDIV]
    ldr r2, =0x8001
    cmp r1, r2
    bne fail
    ldr r1, [r0, #PLL_DIV2]
    cmp r1, r2
    bne fail
    ldr r1, [r0, #PLL_DIV6]
    ldr r2, =0x8000
    cmp r1, r2
    bne fail

    /* Exercise the documented GOSET divider transition, then restore /2. */
    ldr r2, =0x8002
    str r2, [r0, #PLL_DIV2]
    mov r2, #1
    str r2, [r0, #PLL_CMD]
1:
    ldr r2, [r0, #PLL_STAT]
    tst r2, #1
    bne 1b
    ldr r2, [r0, #PLL_DIV2]
    ldr r3, =0x8002
    cmp r2, r3
    bne fail
    ldr r2, =0x8001
    str r2, [r0, #PLL_DIV2]
    mov r2, #1
    str r2, [r0, #PLL_CMD]
2:
    ldr r2, [r0, #PLL_STAT]
    tst r2, #1
    bne 2b

    /* Transition PSC0 module 6 through sync-reset and back to enabled. */
    ldr r0, =PSC0_BASE
    ldr r1, [r0, #PSC_MDSTAT6]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail
    ldr r1, [r0, #PSC_MDCTL6]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_SYNCRESET
    str r1, [r0, #PSC_MDCTL6]
    mov r1, #1
    str r1, [r0, #PSC_PTCMD]
3:
    ldr r1, [r0, #PSC_PTSTAT]
    tst r1, #1
    bne 3b
    ldr r1, [r0, #PSC_MDSTAT6]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_SYNCRESET
    bne fail
    ldr r1, [r0, #PSC_MDCTL6]
    bic r1, r1, #PSC_STATE_MASK
    orr r1, r1, #PSC_ENABLE
    str r1, [r0, #PSC_MDCTL6]
    mov r1, #1
    str r1, [r0, #PSC_PTCMD]
4:
    ldr r1, [r0, #PSC_PTSTAT]
    tst r1, #1
    bne 4b
    ldr r1, [r0, #PSC_MDSTAT6]
    and r1, r1, #PSC_STATE_MASK
    cmp r1, #PSC_ENABLE
    bne fail

    /* Validate the EV3 pinmux/suspend presets. */
    ldr r0, =SYSCFG0_BASE
    ldr r1, [r0, #SYSCFG_PINMUX3]
    ldr r2, =0x00001101
    cmp r1, r2
    bne fail
    ldr r1, [r0, #SYSCFG_PINMUX4]
    ldr r2, =0x22002210
    cmp r1, r2
    bne fail
    ldr r1, [r0, #SYSCFG_PINMUX10]
    ldr r2, =0x00222222
    cmp r1, r2
    bne fail
    ldr r1, [r0, #SYSCFG_SUSPSRC]
    ldr r2, =0xf7d6ffff
    cmp r1, r2
    bne fail

    /*
     * AM1808 revision 2.2 disables KICK protection. Prove that deliberately
     * wrong keys have no effect and PINMUX, SUSPSRC and CFGCHIP stay writable.
     */
    mov r1, #0
    str r1, [r0, #SYSCFG_KICK0]
    str r1, [r0, #SYSCFG_KICK1]
    ldr r3, =0x11111111
    str r3, [r0, #SYSCFG_PINMUX10]
    ldr r1, [r0, #SYSCFG_PINMUX10]
    cmp r1, r3
    bne fail
    ldr r2, =0x00222222
    str r2, [r0, #SYSCFG_PINMUX10]

    ldr r3, =0x12345678
    str r3, [r0, #SYSCFG_SUSPSRC]
    ldr r1, [r0, #SYSCFG_SUSPSRC]
    cmp r1, r3
    bne fail
    ldr r2, =0xf7d6ffff
    str r2, [r0, #SYSCFG_SUSPSRC]

    ldr r3, =0x00000555
    str r3, [r0, #SYSCFG_CFGCHIP2]
    ldr r1, [r0, #SYSCFG_CFGCHIP2]
    cmp r1, r3
    bne fail
    mov r2, #0
    str r2, [r0, #SYSCFG_CFGCHIP2]

    /* Correct keys are likewise architecturally inert on revision 2.2. */
    ldr r1, =KICK0_KEY
    str r1, [r0, #SYSCFG_KICK0]
    ldr r1, =KICK1_KEY
    str r1, [r0, #SYSCFG_KICK1]
    ldr r3, =0x33333333
    str r3, [r0, #SYSCFG_PINMUX10]
    ldr r1, [r0, #SYSCFG_PINMUX10]
    cmp r1, r3
    bne fail
    ldr r2, =0x00222222
    str r2, [r0, #SYSCFG_PINMUX10]

    ldr r1, =success_message
    b print
fail:
    ldr r1, =failure_message
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
    .asciz "EV3 PSC PLL PINMUX OK\n"
failure_message:
    .asciz "EV3 PSC PLL PINMUX FAIL\n"
