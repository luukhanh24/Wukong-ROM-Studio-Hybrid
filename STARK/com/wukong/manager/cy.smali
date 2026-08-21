.class final Lcom/wukong/manager/cy;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x7436b3b5

.field private static final f:I = 0x58568852

.field private static final g:I = 0x1cc8cdd1

.field private static final h:I = 0x43e04769

.field private static final i:I = 0x5ba5109


# direct methods
.method private constructor <init>()V
    .registers 1

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private static e(II)I
    .registers 5

    xor-int v0, p0, p1

    .line 14
    invoke-static {p0, p1}, Lcom/wukong/manager/cp;->e(II)I

    move-result v1

    xor-int/2addr v0, v1

    xor-int v1, p1, v0

    and-int/lit8 v1, v1, 0xf

    add-int/lit8 v1, v1, 0x1

    const v2, 0x58568852

    xor-int/2addr v2, p1

    .line 16
    invoke-static {v0, v2}, Lcom/wukong/manager/bb;->e(II)I

    move-result v2

    add-int/2addr v0, v2

    invoke-static {v0, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v0

    const v1, 0x1cc8cdd1

    xor-int/2addr v1, v0

    .line 17
    invoke-static {p1, v1}, Lcom/wukong/manager/be;->e(II)I

    move-result v1

    xor-int/2addr v0, v1

    xor-int/2addr p0, v0

    const v1, 0x43e04769

    xor-int/2addr p1, v1

    .line 18
    invoke-static {p0, p1}, Lcom/wukong/manager/ap;->e(II)I

    move-result p0

    add-int/2addr v0, p0

    ushr-int/lit8 p0, v0, 0x10

    xor-int/2addr p0, v0

    return p0
.end method

.method private static f(II)I
    .registers 4

    xor-int v0, p0, p1

    const v1, 0x58568852

    xor-int/2addr v1, v0

    .line 23
    invoke-static {p0, p1}, Lcom/wukong/manager/cy;->e(II)I

    move-result p1

    xor-int/2addr p1, v1

    const v1, 0x1cc8cdd1

    add-int/2addr p1, v1

    and-int/lit8 v1, v0, 0xf

    add-int/lit8 v1, v1, 0x5

    .line 24
    invoke-static {p1, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p1

    ushr-int/lit8 v1, p1, 0xd

    xor-int/2addr p1, v1

    const v1, 0x43e04769

    add-int/2addr p1, v1

    ushr-int/lit8 v1, p1, 0x7

    xor-int/2addr p1, v1

    ushr-int/lit8 p0, p0, 0x3

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x3

    .line 27
    invoke-static {p1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    .line 28
    invoke-static {p0, v0}, Lcom/wukong/manager/cy;->e(II)I

    move-result p1

    xor-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static g(II)I
    .registers 3

    const v0, 0x41c64e6d

    mul-int/2addr v0, p0

    xor-int/2addr v0, p1

    mul-int/lit8 p0, p0, 0x1f

    add-int/2addr p0, p1

    .line 141
    invoke-static {v0, p0}, Lcom/wukong/manager/cy;->f(II)I

    move-result p0

    and-int/lit16 p0, p0, 0xff

    return p0
.end method

.method public static h(ILjava/lang/Object;)I
    .registers 5

    if-nez p1, :cond_4

    const/4 p1, 0x0

    goto :goto_8

    .line 32
    :cond_4
    invoke-static {p1}, Ljava/lang/System;->identityHashCode(Ljava/lang/Object;)I

    move-result p1

    :goto_8
    const v0, 0x5ba5109

    xor-int/2addr p0, v0

    const v0, 0x1cc8cdd1

    xor-int/2addr p1, v0

    .line 33
    invoke-static {p0, p1}, Lcom/wukong/manager/cy;->f(II)I

    move-result p0

    .line 34
    sget p1, Lcom/wukong/manager/cy;->e:I

    xor-int v0, p0, p1

    xor-int/lit16 v0, v0, 0xbd

    ushr-int/lit8 v1, v0, 0xb

    xor-int/2addr v1, v0

    and-int/lit8 v1, v1, 0x1f

    const/4 v2, 0x0

    packed-switch v1, :pswitch_data_12a

    shl-int/lit8 v1, p1, 0x3

    ushr-int/lit8 p1, p1, 0x5

    xor-int/2addr p1, v1

    :goto_28
    xor-int/2addr p1, v0

    goto/16 :goto_118

    :pswitch_2b  #0x1f
    add-int/lit8 p1, v0, 0x1f

    .line 130
    invoke-static {p1, v2}, Lcom/wukong/manager/p;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_32  #0x1e
    add-int/lit8 p1, v0, 0x1e

    .line 127
    invoke-static {p1, v2}, Lcom/wukong/manager/c;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_39  #0x1d
    add-int/lit8 p1, v0, 0x1d

    .line 124
    invoke-static {p1, v2}, Lcom/wukong/manager/bn;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_40  #0x1c
    add-int/lit8 p1, v0, 0x1c

    .line 121
    invoke-static {p1, v2}, Lcom/wukong/manager/ag;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_47  #0x1b
    add-int/lit8 p1, v0, 0x1b

    .line 118
    invoke-static {p1, v2}, Lcom/wukong/manager/cc;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_4e  #0x1a
    add-int/lit8 p1, v0, 0x1a

    .line 115
    invoke-static {p1, v2}, Lcom/wukong/manager/cm;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_55  #0x19
    add-int/lit8 p1, v0, 0x19

    .line 112
    invoke-static {p1, v2}, Lcom/wukong/manager/ck;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_5c  #0x18
    add-int/lit8 p1, v0, 0x18

    .line 109
    invoke-static {p1, v2}, Lcom/wukong/manager/cd;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_63  #0x17
    add-int/lit8 p1, v0, 0x17

    .line 106
    invoke-static {p1, v2}, Lcom/wukong/manager/ch;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_6a  #0x16
    add-int/lit8 p1, v0, 0x16

    .line 103
    invoke-static {p1, v2}, Lcom/wukong/manager/bl;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_71  #0x15
    add-int/lit8 p1, v0, 0x15

    .line 100
    invoke-static {p1, v2}, Lcom/wukong/manager/y;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_78  #0x14
    add-int/lit8 p1, v0, 0x14

    .line 97
    invoke-static {p1, v2}, Lcom/wukong/manager/an;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_7f  #0x13
    add-int/lit8 p1, v0, 0x13

    .line 94
    invoke-static {p1, v2}, Lcom/wukong/manager/cb;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_86  #0x12
    add-int/lit8 p1, v0, 0x12

    .line 91
    invoke-static {p1, v2}, Lcom/wukong/manager/j;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_8d  #0x11
    add-int/lit8 p1, v0, 0x11

    .line 88
    invoke-static {p1, v2}, Lcom/wukong/manager/ci;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_94  #0x10
    add-int/lit8 p1, v0, 0x10

    .line 85
    invoke-static {p1, v2}, Lcom/wukong/manager/ba;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_9b  #0xf
    add-int/lit8 p1, v0, 0xf

    .line 82
    invoke-static {p1, v2}, Lcom/wukong/manager/cq;->f(ILjava/lang/Object;)I

    move-result p1

    goto :goto_28

    :pswitch_a2  #0xe
    add-int/lit8 p1, v0, 0xe

    .line 79
    invoke-static {p1, v2}, Lcom/wukong/manager/bz;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_aa  #0xd
    add-int/lit8 p1, v0, 0xd

    .line 76
    invoke-static {p1, v2}, Lcom/wukong/manager/bp;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_b2  #0xc
    add-int/lit8 p1, v0, 0xc

    .line 73
    invoke-static {p1, v2}, Lcom/wukong/manager/bt;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_ba  #0xb
    add-int/lit8 p1, v0, 0xb

    .line 70
    invoke-static {p1, v2}, Lcom/wukong/manager/e;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_c2  #0xa
    add-int/lit8 p1, v0, 0xa

    .line 67
    invoke-static {p1, v2}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_ca  #0x9
    add-int/lit8 p1, v0, 0x9

    .line 64
    invoke-static {p1, v2}, Lcom/wukong/manager/as;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_d2  #0x8
    add-int/lit8 p1, v0, 0x8

    .line 61
    invoke-static {p1, v2}, Lcom/wukong/manager/aw;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_da  #0x7
    add-int/lit8 p1, v0, 0x7

    .line 58
    invoke-static {p1, v2}, Lcom/wukong/manager/al;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_e2  #0x6
    add-int/lit8 p1, v0, 0x6

    .line 55
    invoke-static {p1, v2}, Lcom/wukong/manager/q;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_ea  #0x5
    add-int/lit8 p1, v0, 0x5

    .line 52
    invoke-static {p1, v2}, Lcom/wukong/manager/ad;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_f2  #0x4
    add-int/lit8 p1, v0, 0x4

    .line 49
    invoke-static {p1, v2}, Lcom/wukong/manager/br;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_fa  #0x3
    add-int/lit8 p1, v0, 0x3

    .line 46
    invoke-static {p1, v2}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_102  #0x2
    add-int/lit8 p1, v0, 0x2

    .line 43
    invoke-static {p1, v2}, Lcom/wukong/manager/au;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    :pswitch_10a  #0x1
    add-int/lit8 p1, v0, 0x1

    .line 40
    invoke-static {p1, v2}, Lcom/wukong/manager/bh;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    .line 37
    :pswitch_112  #0x0
    invoke-static {v0, v2}, Lcom/wukong/manager/cp;->f(ILjava/lang/Object;)I

    move-result p1

    goto/16 :goto_28

    .line 136
    :goto_118
    sget v0, Lcom/wukong/manager/cy;->e:I

    xor-int/2addr p1, v0

    xor-int/lit16 p1, p1, 0xbd

    const/4 v0, 0x3

    invoke-static {p1, v0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p1

    const v0, 0x45d9f3b

    add-int/2addr p1, v0

    sput p1, Lcom/wukong/manager/cy;->e:I

    return p0

    nop

    :pswitch_data_12a
    .packed-switch 0x0
        :pswitch_112  #00000000
        :pswitch_10a  #00000001
        :pswitch_102  #00000002
        :pswitch_fa  #00000003
        :pswitch_f2  #00000004
        :pswitch_ea  #00000005
        :pswitch_e2  #00000006
        :pswitch_da  #00000007
        :pswitch_d2  #00000008
        :pswitch_ca  #00000009
        :pswitch_c2  #0000000a
        :pswitch_ba  #0000000b
        :pswitch_b2  #0000000c
        :pswitch_aa  #0000000d
        :pswitch_a2  #0000000e
        :pswitch_9b  #0000000f
        :pswitch_94  #00000010
        :pswitch_8d  #00000011
        :pswitch_86  #00000012
        :pswitch_7f  #00000013
        :pswitch_78  #00000014
        :pswitch_71  #00000015
        :pswitch_6a  #00000016
        :pswitch_63  #00000017
        :pswitch_5c  #00000018
        :pswitch_55  #00000019
        :pswitch_4e  #0000001a
        :pswitch_47  #0000001b
        :pswitch_40  #0000001c
        :pswitch_39  #0000001d
        :pswitch_32  #0000001e
        :pswitch_2b  #0000001f
    .end packed-switch
.end method

.method public static i(II)Z
    .registers 5

    const v0, 0x5ba5109

    xor-int v1, p1, v0

    const v2, 0x1cc8cdd1

    .line 144
    invoke-static {v1, v2}, Lcom/wukong/manager/cy;->f(II)I

    move-result v1

    xor-int v2, p0, p1

    .line 145
    invoke-static {v2, v0}, Lcom/wukong/manager/cy;->f(II)I

    move-result v2

    xor-int/2addr p1, v1

    .line 146
    invoke-static {p1, v0}, Lcom/wukong/manager/cy;->f(II)I

    move-result p1

    if-ne p0, v1, :cond_1d

    if-ne v2, p1, :cond_1d

    const/4 p0, 0x1

    return p0

    :cond_1d
    const/4 p0, 0x0

    return p0
.end method
