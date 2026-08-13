.class final Lcom/wukong/manager/bt;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0xd6bde8e

.field private static f:I = 0x177162e2

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 4

    const v0, 0x135231a7

    const v1, 0x5d58c92d

    const v2, 0x63268338

    const v3, 0x5b476a69

    .line 3521
    filled-new-array {v2, v3, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/bt;->g:[I

    return-void
.end method

.method private constructor <init>()V
    .registers 1

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static e(II)I
    .registers 6

    xor-int/2addr p0, p1

    const p1, 0x7fffffff

    and-int v0, p0, p1

    const v1, 0x3a9344af

    xor-int/2addr v1, p0

    .line 3556
    sget-object v2, Lcom/wukong/manager/bt;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x58c46647

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 3557
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 3560
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x63a617e9

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 3561
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 3524
    sget v0, Lcom/wukong/manager/bt;->e:I

    xor-int/2addr p0, v0

    const/4 v0, 0x0

    .line 3525
    :goto_4
    sget-object v1, Lcom/wukong/manager/bt;->g:[I

    array-length v2, v1

    if-ge v0, v2, :cond_1b

    .line 3526
    aget v1, v1, v0

    add-int/2addr p0, v1

    add-int/2addr p0, v0

    and-int/lit8 v1, v0, 0x7

    add-int/lit8 v1, v1, 0x1

    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v1, p0, 0xb

    xor-int/2addr p0, v1

    add-int/lit8 v0, v0, 0x1

    goto :goto_4

    :cond_1b
    if-eqz p1, :cond_22

    .line 3529
    invoke-static {p1}, Ljava/lang/System;->identityHashCode(Ljava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 3530
    :cond_22
    sget p1, Lcom/wukong/manager/bt;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/bt;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 3534
    sget v0, Lcom/wukong/manager/bt;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/bt;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 3535
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 3536
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 3537
    sget-object p1, Lcom/wukong/manager/bt;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x46

    and-int/lit8 p1, p1, 0x3

    if-ne p0, p1, :cond_1f

    const/4 p0, 0x1

    return p0

    :cond_1f
    const/4 p0, 0x0

    return p0
.end method

.method public static h(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .registers 4

    if-ne p0, p1, :cond_3

    goto :goto_1a

    .line 3541
    :cond_3
    sget v0, Lcom/wukong/manager/bt;->e:I

    sget v1, Lcom/wukong/manager/bt;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result v0

    .line 3542
    invoke-static {v0, p1}, Lcom/wukong/manager/bi;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 3543
    sget v1, Lcom/wukong/manager/bt;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/bt;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x46

    .line 3547
    invoke-static {p0, p1}, Lcom/wukong/manager/bt;->f(ILjava/lang/Object;)I

    move-result p0

    .line 3548
    invoke-static {p0, p1}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 3549
    sget v0, Lcom/wukong/manager/bt;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 3550
    :cond_17
    sget p1, Lcom/wukong/manager/bt;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bi;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
