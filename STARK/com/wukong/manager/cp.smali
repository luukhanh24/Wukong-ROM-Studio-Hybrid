.class final Lcom/wukong/manager/cp;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x74387dda

.field private static f:I = 0x12faa43e

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 335
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/cp;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x27ecd7be
        0x4cdaf483  # 1.14795544E8f
        0x23d9a757
        0x12c1579d
        0x3af39f98
        0x799749e5
        0x3de68900
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

    const v1, 0x1ffcaafc

    xor-int/2addr v1, p0

    .line 367
    sget-object v2, Lcom/wukong/manager/cp;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x32d6b1c1

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 368
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 371
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x317f409e

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 372
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 339
    :try_start_0
    sget v0, Lcom/wukong/manager/cp;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/cp;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/cp;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 340
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 341
    :cond_1e
    sget p1, Lcom/wukong/manager/cp;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/cp;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 345
    sget v0, Lcom/wukong/manager/cp;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/cp;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 346
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 347
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 348
    sget-object p1, Lcom/wukong/manager/cp;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x3

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

    .line 352
    :cond_3
    sget v0, Lcom/wukong/manager/cp;->e:I

    sget v1, Lcom/wukong/manager/cp;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/am;->f(ILjava/lang/Object;)I

    move-result v0

    .line 353
    invoke-static {v0, p1}, Lcom/wukong/manager/bv;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 354
    sget v1, Lcom/wukong/manager/cp;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/cp;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x3

    .line 358
    invoke-static {p0, p1}, Lcom/wukong/manager/cp;->f(ILjava/lang/Object;)I

    move-result p0

    .line 359
    invoke-static {p0, p1}, Lcom/wukong/manager/bs;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 360
    sget v0, Lcom/wukong/manager/cp;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/am;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 361
    :cond_17
    sget p1, Lcom/wukong/manager/cp;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bv;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
