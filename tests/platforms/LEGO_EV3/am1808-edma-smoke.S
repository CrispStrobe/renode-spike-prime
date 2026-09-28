/* SPDX-License-Identifier: MIT */
/*
 * Independently authored AM1808 EDMA3 -> AINTC executable proof.
 * Register layout and event mapping follow TI SPRUH82C chapters 11 and 17.
 * Build normally for software channel 0, or define EDMA_HW16 for the public
 * MMC/SD0 receive hardware-event mapping. No LEGO firmware material is used.
 */

.syntax unified
.cpu arm926ej-s
.arm

.equ UART1_THR,          0x01d0c000
.equ EDMA0_CC,           0x01c00000
.equ EDMA_DRAE0,         0x340
.equ EDMA_SHADOW,        0x01c02000
.equ EDMA_ESR,           0x10
.equ EDMA_EESR,          0x30
.equ EDMA_IESR,          0x60
.equ EDMA_IPR,           0x68
.equ EDMA_ICR,           0x70
.equ EDMA_PARAM,         0x4000
.equ PARAM_OPT,          0x00
.equ PARAM_SRC,          0x04
.equ PARAM_A_B_CNT,      0x08
.equ PARAM_DST,          0x0c
.equ PARAM_BIDX,         0x10
.equ PARAM_LINK_BCNTRLD, 0x14
.equ PARAM_CIDX,         0x18
.equ PARAM_CCNT,         0x1c

.equ AINTC_GER,          0xfffee010
.equ AINTC_SICR,         0xfffee024
.equ AINTC_EISR,         0xfffee028
.equ AINTC_HIEISR,       0xfffee034
.equ AINTC_CMR2,         0xfffee408
.equ EDMA0_COMPLETION,   11

.equ SOURCE,             0x80000000
.equ DESTINATION,        0x80000100

.ifdef EDMA_HW16
.equ TEST_CHANNEL,       16
.equ TEST_MASK,          0x00010000
.equ TEST_OPT,           0x00110008 /* STATIC, TCINTEN, TCC=16 */
.equ PARAM_BASE,         EDMA0_CC + EDMA_PARAM + 16 * 0x20
.else
.equ TEST_CHANNEL,       0
.equ TEST_MASK,          0x00000001
.equ TEST_OPT,           0x00100008 /* STATIC, TCINTEN, TCC=0 */
.equ PARAM_BASE,         EDMA0_CC + EDMA_PARAM
.endif

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

    /* Initialize a value pattern and a deliberately different destination. */
    ldr r0, =SOURCE
    ldr r1, =0x01234567
    str r1, [r0, #0]
    ldr r1, =0x89abcdef
    str r1, [r0, #4]
    ldr r1, =0x55aa33cc
    str r1, [r0, #8]
    ldr r1, =0xf00dcafe
    str r1, [r0, #12]
    ldr r0, =DESTINATION
    ldr r1, =0xdeadbeef
    str r1, [r0, #0]
    str r1, [r0, #4]
    str r1, [r0, #8]
    str r1, [r0, #12]

    /* One 16-byte A-synchronized transfer; fixed channel-to-PaRAM mapping. */
    ldr r0, =PARAM_BASE
    ldr r1, =TEST_OPT
    str r1, [r0, #PARAM_OPT]
    ldr r1, =SOURCE
    str r1, [r0, #PARAM_SRC]
    ldr r1, =0x00010010  /* BCNT=1, ACNT=16 */
    str r1, [r0, #PARAM_A_B_CNT]
    ldr r1, =DESTINATION
    str r1, [r0, #PARAM_DST]
    ldr r1, =0x00100010  /* DSTBIDX=16, SRCBIDX=16 */
    str r1, [r0, #PARAM_BIDX]
    ldr r1, =0x0000ffff  /* no link */
    str r1, [r0, #PARAM_LINK_BCNTRLD]
    mov r1, #0
    str r1, [r0, #PARAM_CIDX]
    mov r1, #1
    str r1, [r0, #PARAM_CCNT]

    /* Region 0 shadow registers are gated by DRAE0 after reset. */
    ldr r0, =EDMA0_CC
    ldr r1, =TEST_MASK
    str r1, [r0, #EDMA_DRAE0]

    /* Route the physical EDMA0 completion event 11 to AINTC IRQ host 1. */
    ldr r0, =AINTC_CMR2
    ldr r1, =0x01000000
    str r1, [r0]
    ldr r0, =AINTC_EISR
    mov r1, #EDMA0_COMPLETION
    str r1, [r0]
    ldr r0, =AINTC_HIEISR
    mov r1, #1
    str r1, [r0]
    ldr r0, =AINTC_GER
    str r1, [r0]

    ldr r0, =EDMA_SHADOW
    ldr r1, =TEST_MASK
    str r1, [r0, #EDMA_IESR]
.ifdef EDMA_HW16
    /* Enabling event 16 drains the request latched before the CPU started. */
    str r1, [r0, #EDMA_EESR]
.else
    /* A software ESR trigger does not depend on EER. */
    str r1, [r0, #EDMA_ESR]
.endif
    msr cpsr_c, #0x53

    /* Bounded, active wait: missing physical IRQ produces explicit evidence. */
    ldr r8, =0x00500000
1:
    cmp r9, #1
    beq validate
    cmp r9, #2
    beq fail_irq
    subs r8, r8, #1
    bne 1b
    b fail_timeout

validate:
    ldr r0, =SOURCE
    ldr r1, =DESTINATION
    ldmia r0, {r2-r5}
    ldmia r1, {r6-r8, r10}
    cmp r2, r6
    bne fail_data
    cmp r3, r7
    bne fail_data
    cmp r4, r8
    bne fail_data
    cmp r5, r10
    bne fail_data
.ifdef EDMA_HW16
    ldr r1, =success_hw_message
.else
    ldr r1, =success_message
.endif
    b print

fail_irq:
    ldr r1, =failure_irq_message
    b print
fail_timeout:
    ldr r1, =failure_timeout_message
    b print
fail_data:
    ldr r1, =failure_data_message

print:
    ldr r0, =UART1_THR
2:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 3f
    strb r2, [r0]
    b 2b
3:
    b 3b

irq:
    stmfd sp!, {r0-r2, lr}
    ldr r0, =EDMA_SHADOW
    ldr r1, [r0, #EDMA_IPR]
    ldr r2, =TEST_MASK
    tst r1, r2
    moveq r9, #2
    movne r9, #1
    str r2, [r0, #EDMA_ICR]
    ldr r0, =AINTC_SICR
    mov r1, #EDMA0_COMPLETION
    str r1, [r0]
    ldmfd sp!, {r0-r2, lr}
    subs pc, lr, #4

success_message:
    .asciz "EV3 EDMA IRQ\n"
success_hw_message:
    .asciz "EV3 EDMA HW16 IRQ\n"
failure_irq_message:
    .asciz "EV3 EDMA FAIL IRQ\n"
failure_timeout_message:
    .asciz "EV3 EDMA FAIL TIMEOUT\n"
failure_data_message:
    .asciz "EV3 EDMA FAIL DATA\n"
