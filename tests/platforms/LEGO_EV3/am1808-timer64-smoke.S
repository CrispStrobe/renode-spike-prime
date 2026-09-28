/* SPDX-License-Identifier: MIT */
/* Independent Timer64P0 -> AINTC -> ARM926 executable proof. */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000
.equ TIMER0_PRD12,       0x01c20018
.equ TIMER0_PRD34,       0x01c2001c
.equ TIMER0_TCR,         0x01c20020
.equ TIMER0_TGCR,        0x01c20024
.equ TIMER0_INTCTLSTAT,  0x01c20044
.equ AINTC_GER,          0xfffee010
.equ AINTC_SICR,         0xfffee024
.equ AINTC_EISR,         0xfffee028
.equ AINTC_HIEISR,       0xfffee034
.equ AINTC_CMR5,         0xfffee414
.equ TIMER0_TINT12,      21

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

    /* Event 21 occupies CMR5 byte 1; channel/host 1 is IRQ. */
    ldr r0, =AINTC_CMR5
    mov r1, #0x100
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #TIMER0_TINT12
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]

    /* 24 MHz / 240000 clocks = 10 ms, one-shot 64-bit mode. */
    ldr r0, =TIMER0_PRD12
    ldr r1, =239999
    str r1, [r0]
    ldr r0, =TIMER0_PRD34
    mov r1, #0
    str r1, [r0]
    ldr r0, =TIMER0_INTCTLSTAT
    mov r1, #1
    str r1, [r0]
    ldr r0, =TIMER0_TGCR
    mov r1, #3
    str r1, [r0]

    msr cpsr_c, #0x53
    ldr r0, =TIMER0_TCR
    mov r1, #0x40
    str r1, [r0]

1:
    add r2, r2, #1
    eor r3, r3, r2, ror #5
    b 1b

irq:
    stmfd sp!, {r0-r2, lr}
    ldr r0, =TIMER0_INTCTLSTAT
    mov r1, #3              /* keep enable, W1C period status */
    str r1, [r0]
    ldr r0, =AINTC_SICR
    mov r1, #TIMER0_TINT12
    str r1, [r0]
    ldr r0, =UART1_THR
    adr r1, message
2:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 3f
    strb r2, [r0]
    b 2b
3:
    ldmfd sp!, {r0-r2, lr}
    subs pc, lr, #4

message:
    .asciz "EV3 TIMER64 IRQ\n"
