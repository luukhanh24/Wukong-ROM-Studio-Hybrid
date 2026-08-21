.class final Lcom/wukong/manager/ab;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x213cca0c

.field private static f:I = 0x7a8a3cab

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/16 v0, 0x8

    .line 1570
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ab;->g:[I

    return-void

    :array_a
    .array-data 4
        0x145017dc
        0x49c9800e  # 1650689.8f
        0x1e53ac38
        0x1caca20e
        0x31a83f75
        0x14d75b85
        0x5d2f3f2c
        0x6bc3a777
    .end array-data
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

    const v1, 0x6d4b9f2e

    xor-int/2addr v1, p0

    .line 1604
    sget-object v2, Lcom/wukong/manager/ab;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x4d12c9e9  # 1.5391912E8f

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1605
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1608
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x366d838b

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1609
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 1573
    sget-object p1, Lcom/wukong/manager/ab;->g:[I

    const v0, 0x7fffffff

    and-int/2addr v0, p0

    array-length v1, p1

    rem-int/2addr v0, v1

    aget p1, p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_c
    const/4 v0, 0x7

    if-ge p1, v0, :cond_22

    .line 1575
    sget v1, Lcom/wukong/manager/ab;->e:I

    mul-int/lit16 v2, p1, 0x101

    xor-int/2addr v1, v2

    add-int/2addr p0, v1

    const/4 v1, 0x5

    .line 1576
    invoke-static {p0, v1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result v1

    invoke-static {p0, v0}, Ljava/lang/Integer;->rotateRight(II)I

    move-result p0

    xor-int/2addr p0, v1

    add-int/lit8 p1, p1, 0x1

    goto :goto_c

    .line 1578
    :cond_22
    sget p1, Lcom/wukong/manager/ab;->e:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/ab;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1582
    sget v0, Lcom/wukong/manager/ab;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ab;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1583
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1584
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ao;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1585
    sget-object p1, Lcom/wukong/manager/ab;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x1d

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

    .line 1589
    :cond_3
    sget v0, Lcom/wukong/manager/ab;->e:I

    sget v1, Lcom/wukong/manager/ab;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1590
    invoke-static {v0, p1}, Lcom/wukong/manager/cs;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1591
    sget v1, Lcom/wukong/manager/ab;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ab;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x1d

    .line 1595
    invoke-static {p0, p1}, Lcom/wukong/manager/ab;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1596
    invoke-static {p0, p1}, Lcom/wukong/manager/ao;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1597
    sget v0, Lcom/wukong/manager/ab;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1598
    :cond_17
    sget p1, Lcom/wukong/manager/ab;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/cs;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
