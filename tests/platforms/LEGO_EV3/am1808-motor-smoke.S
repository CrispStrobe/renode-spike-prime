/* SPDX-License-Identifier: MIT */
/* Original ARM926 proof of four PWM sources, H-bridge GPIO and encoder IRQs.
 * Host writes phase at ffff1810: 0 forward, 1 reverse, 2 brake, 3 coast.
 * ffff1814 contains encoder IRQ seen bits A/B/C/D; ffff1818 acknowledges
 * configured phase. Host gives forward/reverse 100ms and stopped phases 20ms.
 */
.syntax unified
.cpu arm926ej-s
.arm
.equ GPIO, 0x01e26000
.equ PHASE, 0xffff1810
.equ SEEN, 0xffff1814
.equ ACK, 0xffff1818
.equ PWM1, 0x01f02000
.equ ECAP0, 0x01f06000
.equ ECAP1, 0x01f07000
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
    /* Enable GPIO, eHRPWM and eCAP clocks through PSC1. */
    ldr r0, =0x01e27000
    ldr r1, [r0, #0xa0c]
    bic r1, r1, #0x1f
    orr r1, r1, #3
    str r1, [r0, #0xa0c]
    ldr r1, [r0, #0xa44]
    bic r1, r1, #0x1f
    orr r1, r1, #3
    str r1, [r0, #0xa44]
    ldr r1, [r0, #0xa50]
    bic r1, r1, #0x1f
    orr r1, r1, #3
    str r1, [r0, #0xa50]
    mov r1, #1
    str r1, [r0, #0x120]
    ldr r1, [r0, #0x80c]
    and r1, r1, #0x1f
    cmp r1, #3
    bne fail
    ldr r1, [r0, #0x844]
    and r1, r1, #0x1f
    cmp r1, #3
    bne fail
    ldr r1, [r0, #0x850]
    and r1, r1, #0x1f
    cmp r1, #3
    bne fail
    /* eHRPWM1A/B: 150MHz /4 /37500 =1kHz, 50% high. */
    ldr r0, =PWM1
    ldr r1, =0x103
    strh r1, [r0]
    ldr r1, =37499
    strh r1, [r0, #0x0a]
    mov r1, #0x50
    strh r1, [r0, #0x0e]
    ldr r1, =18750
    strh r1, [r0, #0x12]
    strh r1, [r0, #0x14]
    mov r1, #0x12
    strh r1, [r0, #0x16]
    ldr r1, =0x102
    strh r1, [r0, #0x18]
    mov r1, #0x100
    strh r1, [r0]
    /* eCAP0/1 APWM: 150MHz /150000 =1kHz, 50%. */
    ldr r0, =ECAP0
    bl configure_ecap
    ldr r0, =ECAP1
    bl configure_ecap
    ldr r5, =GPIO
    /* Bridge outputs: 63/54,33/3,104/89,83/90. */
    ldr r1, [r5, #0x10]
    bic r1, r1, #8
    str r1, [r5, #0x10]
    ldr r1, [r5, #0x38]
    ldr r2, =0x80400002
    bic r1, r1, r2
    str r1, [r5, #0x38]
    ldr r1, [r5, #0x60]
    ldr r2, =0x06080000
    bic r1, r1, r2
    str r1, [r5, #0x60]
    ldr r1, [r5, #0x88]
    bic r1, r1, #0x100
    str r1, [r5, #0x88]
    /* Physical encoder A pins91/88/93/105, banks5/6. */
    ldr r1, =0x29000000
    str r1, [r5, #0x74]
    str r1, [r5, #0x7c]
    mov r1, #0x200
    str r1, [r5, #0x9c]
    str r1, [r5, #0xa4]
    mov r1, #0x60
    str r1, [r5, #8]
    ldr r0, =SEEN
    mov r1, #0
    str r1, [r0]
    ldr r0, =0xfffee42c
    mov r1, #0x01000000
    str r1, [r0]
    mov r1, #1
    str r1, [r0, #4]
    ldr r0, =0xfffee028
    mov r1, #47
    str r1, [r0]
    mov r1, #48
    str r1, [r0]
    ldr r0, =0xfffee034
    mov r1, #1
    str r1, [r0]
    ldr r0, =0xfffee010
    str r1, [r0]
    bl clear_bridges
    bl set_forward
    mov r6, #0
    bl acknowledge
    msr cpsr_c, #0x53
wait_reverse:
    ldr r0, =PHASE
    ldr r1, [r0]
    cmp r1, #0
    beq wait_reverse
    cmp r1, #1
    bne fail
    ldr r0, =SEEN
    ldr r1, [r0]
    cmp r1, #15
    bne fail
    /* Mask CPU IRQ while resetting the per-phase encoder receipt. */
    msr cpsr_c, #0xd3
    bl clear_bridges
    mov r1, #0
    ldr r0, =SEEN
    str r1, [r0]
    bl set_reverse
    mov r6, #1
    bl acknowledge
    msr cpsr_c, #0x53
wait_brake:
    ldr r0, =PHASE
    ldr r1, [r0]
    cmp r1, #1
    beq wait_brake
    cmp r1, #2
    bne fail
    ldr r0, =SEEN
    ldr r1, [r0]
    cmp r1, #15
    bne fail
    bl set_forward /* both bridge inputs high: brake */
    mov r6, #2
    bl acknowledge
wait_coast:
    ldr r0, =PHASE
    ldr r1, [r0]
    cmp r1, #2
    beq wait_coast
    cmp r1, #3
    bne fail
    bl clear_bridges
    mov r6, #3
    bl acknowledge
    ldr r1, =success
    b print
configure_ecap:
    ldr r1, =149999
    str r1, [r0, #8]
    ldr r1, =75000
    str r1, [r0, #0xc]
    ldr r1, =0x210
    strh r1, [r0, #0x2a]
    bx lr
clear_bridges:
    mov r1, #8
    str r1, [r5, #0x1c]
    ldr r1, =0x80400002
    str r1, [r5, #0x44]
    ldr r1, =0x06080000
    str r1, [r5, #0x6c]
    mov r1, #0x100
    str r1, [r5, #0x94]
    bx lr
set_forward:
    ldr r1, =0x80000002
    str r1, [r5, #0x40]
    mov r1, #0x80000
    str r1, [r5, #0x68]
    mov r1, #0x100
    str r1, [r5, #0x90]
    bx lr
set_reverse:
    mov r1, #8
    str r1, [r5, #0x18]
    mov r1, #0x400000
    str r1, [r5, #0x40]
    mov r1, #0x06000000
    str r1, [r5, #0x68]
    bx lr
acknowledge:
    ldr r0, =ACK
    str r6, [r0]
    bx lr
irq:
    stmfd sp!, {r0-r4, lr}
    ldr r0, =0xfffee904
    ldr r4, [r0]
    cmp r4, #47
    beq encoder_irq
    cmp r4, #48
    bne fail
encoder_irq:
    ldr r0, =GPIO
    ldr r1, [r0, #0x84]
    ldr r2, =0x29000000
    and r1, r1, r2
    str r1, [r0, #0x84]
    ldr r2, =SEEN
    ldr r3, [r2]
    tst r1, #0x08000000
    orrne r3, r3, #1
    tst r1, #0x01000000
    orrne r3, r3, #2
    tst r1, #0x20000000
    orrne r3, r3, #4
    ldr r1, [r0, #0xac]
    and r1, r1, #0x200
    str r1, [r0, #0xac]
    cmp r1, #0
    orrne r3, r3, #8
    str r3, [r2]
    ldr r0, =0xfffee024
    mov r1, #47
    str r1, [r0]
    mov r1, #48
    str r1, [r0]
    ldmfd sp!, {r0-r4, lr}
    subs pc, lr, #4
fail:
    ldr r1, =failure
print:
    ldr r0, =0x01d0c000
1:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 2f
    strb r2, [r0]
    b 1b
2:
    b 2b
success:
    .asciz "EV3 MOTOR PWM4 TACHO IRQ47 IRQ48 OK\n"
failure:
    .asciz "EV3 MOTOR FAIL\n"
