.class final Lcom/wukong/manager/au;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x643f3ac5

.field private static f:I = 0x1e974f5f

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 2239
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/au;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x48795d7a
        0x436124dc
        0x383d6073
        0x66e2a44e
        0x3dd7fd85
        0x7df9b2c0
        0x1dbaf0b7
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

    const v1, 0x2cc82aec

    xor-int/2addr v1, p0

    .line 2271
    sget-object v2, Lcom/wukong/manager/au;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x5c9d3829

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2272
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2275
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x65b26ca4

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2276
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 2243
    :try_start_0
    sget v0, Lcom/wukong/manager/au;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/au;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/au;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 2244
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 2245
    :cond_1e
    sget p1, Lcom/wukong/manager/au;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/au;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2249
    sget v0, Lcom/wukong/manager/au;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/au;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2250
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2251
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/f;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2252
    sget-object p1, Lcom/wukong/manager/au;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x2b

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

    .line 2256
    :cond_3
    sget v0, Lcom/wukong/manager/au;->e:I

    sget v1, Lcom/wukong/manager/au;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bc;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2257
    invoke-static {v0, p1}, Lcom/wukong/manager/ae;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2258
    sget v1, Lcom/wukong/manager/au;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/au;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x2b

    .line 2262
    invoke-static {p0, p1}, Lcom/wukong/manager/au;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2263
    invoke-static {p0, p1}, Lcom/wukong/manager/f;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2264
    sget v0, Lcom/wukong/manager/au;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bc;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2265
    :cond_17
    sget p1, Lcom/wukong/manager/au;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/ae;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
