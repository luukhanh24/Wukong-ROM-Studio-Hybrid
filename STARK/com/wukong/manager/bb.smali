.class final Lcom/wukong/manager/bb;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x436d955a

.field private static f:I = 0x63a31d6

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x6

    .line 1001
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/bb;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x22fe74ab
        0x7dc3c23a
        0x413f711c
        0x312f23e
        0x26777cc1
        0x4bd0e45c  # 2.7379896E7f
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

    const v1, 0x2cf316ea

    xor-int/2addr v1, p0

    .line 1036
    sget-object v2, Lcom/wukong/manager/bb;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x3c345c11

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1037
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1040
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x17e3ae32

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1041
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 1004
    sget p1, Lcom/wukong/manager/bb;->e:I

    sget v0, Lcom/wukong/manager/bb;->f:I

    add-int/2addr p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_7
    const/4 v0, 0x5

    if-ge p1, v0, :cond_1e

    .line 1007
    sget-object v0, Lcom/wukong/manager/bb;->g:[I

    array-length v1, v0

    rem-int v1, p1, v1

    aget v0, v0, v1

    add-int/2addr v0, p0

    and-int/lit8 v1, p1, 0xf

    add-int/lit8 v1, v1, 0x1

    invoke-static {v0, v1}, Ljava/lang/Integer;->rotateRight(II)I

    move-result v0

    xor-int/2addr p0, v0

    add-int/lit8 p1, p1, 0x1

    goto :goto_7

    :cond_1e
    mul-int/lit8 p1, p0, 0x21

    ushr-int/lit8 p0, p0, 0x9

    xor-int/2addr p0, p1

    .line 1010
    sput p0, Lcom/wukong/manager/bb;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1014
    sget v0, Lcom/wukong/manager/bb;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/bb;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1015
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1016
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bj;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1017
    sget-object p1, Lcom/wukong/manager/bb;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x11

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

    .line 1021
    :cond_3
    sget v0, Lcom/wukong/manager/bb;->e:I

    sget v1, Lcom/wukong/manager/bb;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/a;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1022
    invoke-static {v0, p1}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1023
    sget v1, Lcom/wukong/manager/bb;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/bb;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x11

    .line 1027
    invoke-static {p0, p1}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1028
    invoke-static {p0, p1}, Lcom/wukong/manager/bj;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1029
    sget v0, Lcom/wukong/manager/bb;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/a;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1030
    :cond_17
    sget p1, Lcom/wukong/manager/bb;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
