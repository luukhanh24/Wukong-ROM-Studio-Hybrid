.class final Lcom/wukong/manager/ak;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x357a85a9

.field private static f:I = 0x95f4141

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 1763
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ak;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x65757825
        0x437719b
        0x27ae949e
        0x7d1b593a
        0x46fc2d5a
        0x5164cad6
        0xa2c1f1a
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

    const v1, 0x7cde7908

    xor-int/2addr v1, p0

    .line 1795
    sget-object v2, Lcom/wukong/manager/ak;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x80dce6d

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1796
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1799
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0xa5d3439

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1800
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 1767
    :try_start_0
    sget v0, Lcom/wukong/manager/ak;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/ak;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/ak;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 1768
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 1769
    :cond_1e
    sget p1, Lcom/wukong/manager/ak;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/ak;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1773
    sget v0, Lcom/wukong/manager/ak;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ak;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1774
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1775
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bn;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1776
    sget-object p1, Lcom/wukong/manager/ak;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x21

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

    .line 1780
    :cond_3
    sget v0, Lcom/wukong/manager/ak;->e:I

    sget v1, Lcom/wukong/manager/ak;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bm;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1781
    invoke-static {v0, p1}, Lcom/wukong/manager/g;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1782
    sget v1, Lcom/wukong/manager/ak;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ak;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x21

    .line 1786
    invoke-static {p0, p1}, Lcom/wukong/manager/ak;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1787
    invoke-static {p0, p1}, Lcom/wukong/manager/bn;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1788
    sget v0, Lcom/wukong/manager/ak;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bm;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1789
    :cond_17
    sget p1, Lcom/wukong/manager/ak;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/g;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
