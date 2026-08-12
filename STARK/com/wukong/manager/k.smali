.class final Lcom/wukong/manager/k;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x144a6dd4

.field private static f:I = 0x2be2cd3c

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 4

    const v0, 0x7091e71c

    const v1, 0x1459a84d

    const v2, 0x34b760af

    const v3, 0x3b56a721

    .line 2331
    filled-new-array {v2, v3, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/k;->g:[I

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

    const v1, 0x4f2da469

    xor-int/2addr v1, p0

    .line 2366
    sget-object v2, Lcom/wukong/manager/k;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x2c1e1716

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2367
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2370
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0xe9ebf57

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2371
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 5

    .line 2334
    sget v0, Lcom/wukong/manager/k;->e:I

    xor-int/2addr p0, v0

    const/4 v0, 0x0

    .line 2335
    :goto_4
    sget-object v1, Lcom/wukong/manager/k;->g:[I

    array-length v2, v1

    if-ge v0, v2, :cond_1b

    .line 2336
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

    .line 2339
    invoke-static {p1}, Ljava/lang/System;->identityHashCode(Ljava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2340
    :cond_22
    sget p1, Lcom/wukong/manager/k;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/k;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2344
    sget v0, Lcom/wukong/manager/k;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/k;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2345
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2346
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/j;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2347
    sget-object p1, Lcom/wukong/manager/k;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x2d

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

    .line 2351
    :cond_3
    sget v0, Lcom/wukong/manager/k;->e:I

    sget v1, Lcom/wukong/manager/k;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bf;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2352
    invoke-static {v0, p1}, Lcom/wukong/manager/aj;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2353
    sget v1, Lcom/wukong/manager/k;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/k;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x2d

    .line 2357
    invoke-static {p0, p1}, Lcom/wukong/manager/k;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2358
    invoke-static {p0, p1}, Lcom/wukong/manager/j;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2359
    sget v0, Lcom/wukong/manager/k;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bf;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2360
    :cond_17
    sget p1, Lcom/wukong/manager/k;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/aj;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
