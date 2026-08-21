.class final Lcom/wukong/manager/am;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0xcc52f2a

.field private static f:I = 0x36252ecd

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 4

    const v0, 0x4fe41195

    const v1, 0x695a20c2

    const v2, 0x490b4041

    const v3, 0xaca1f8d

    .line 665
    filled-new-array {v2, v3, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/am;->g:[I

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

    const v1, 0x6475894

    xor-int/2addr v1, p0

    .line 700
    sget-object v2, Lcom/wukong/manager/am;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x4e588ac9  # 9.082435E8f

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 701
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 704
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x3dbe73

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 705
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 668
    sget v0, Lcom/wukong/manager/am;->e:I

    xor-int/2addr p0, v0

    const/4 v0, 0x0

    .line 669
    :goto_4
    sget-object v1, Lcom/wukong/manager/am;->g:[I

    array-length v2, v1

    if-ge v0, v2, :cond_1b

    .line 670
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

    .line 673
    invoke-static {p1}, Ljava/lang/System;->identityHashCode(Ljava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 674
    :cond_22
    sget p1, Lcom/wukong/manager/am;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/am;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 678
    sget v0, Lcom/wukong/manager/am;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/am;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 679
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 680
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bc;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 681
    sget-object p1, Lcom/wukong/manager/am;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0xa

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

    .line 685
    :cond_3
    sget v0, Lcom/wukong/manager/am;->e:I

    sget v1, Lcom/wukong/manager/am;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result v0

    .line 686
    invoke-static {v0, p1}, Lcom/wukong/manager/ab;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 687
    sget v1, Lcom/wukong/manager/am;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/am;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0xa

    .line 691
    invoke-static {p0, p1}, Lcom/wukong/manager/am;->f(ILjava/lang/Object;)I

    move-result p0

    .line 692
    invoke-static {p0, p1}, Lcom/wukong/manager/bc;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 693
    sget v0, Lcom/wukong/manager/am;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 694
    :cond_17
    sget p1, Lcom/wukong/manager/am;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/ab;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
