.class final Lcom/wukong/manager/ch;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x29b35653

.field private static f:I = 0x17dfe6e8

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x6

    .line 4333
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ch;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x28278972
        0x7baa0fbd
        0x53d181c6
        0x5ed024a8
        0x7ccdc0e9
        0x6c8ee50f
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

    const v1, 0x49a253f5

    xor-int/2addr v1, p0

    .line 4368
    sget-object v2, Lcom/wukong/manager/ch;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x6985ab52

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 4369
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 4372
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x331319be

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 4373
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 4336
    sget p1, Lcom/wukong/manager/ch;->e:I

    sget v0, Lcom/wukong/manager/ch;->f:I

    add-int/2addr p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_7
    const/4 v0, 0x3

    if-ge p1, v0, :cond_1e

    .line 4339
    sget-object v0, Lcom/wukong/manager/ch;->g:[I

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

    .line 4342
    sput p0, Lcom/wukong/manager/ch;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 4346
    sget v0, Lcom/wukong/manager/ch;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ch;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 4347
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 4348
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bq;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 4349
    sget-object p1, Lcom/wukong/manager/ch;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x57

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

    .line 4353
    :cond_3
    sget v0, Lcom/wukong/manager/ch;->e:I

    sget v1, Lcom/wukong/manager/ch;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/ab;->f(ILjava/lang/Object;)I

    move-result v0

    .line 4354
    invoke-static {v0, p1}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 4355
    sget v1, Lcom/wukong/manager/ch;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ch;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x57

    .line 4359
    invoke-static {p0, p1}, Lcom/wukong/manager/ch;->f(ILjava/lang/Object;)I

    move-result p0

    .line 4360
    invoke-static {p0, p1}, Lcom/wukong/manager/bq;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 4361
    sget v0, Lcom/wukong/manager/ch;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/ab;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 4362
    :cond_17
    sget p1, Lcom/wukong/manager/ch;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/co;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
