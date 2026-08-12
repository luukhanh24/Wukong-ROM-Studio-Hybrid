.class final Lcom/wukong/manager/b;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x498dfab

.field private static f:I = 0x75b9f42d

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 5

    const v0, 0x198839be

    const v1, 0x47ee0e0c

    const v2, 0x45526851

    const v3, 0x3333aec4

    const v4, 0x3250e32

    .line 4283
    filled-new-array {v2, v3, v4, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/b;->g:[I

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

    const v1, 0xae78dc2

    xor-int/2addr v1, p0

    .line 4320
    sget-object v2, Lcom/wukong/manager/b;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x37ccd4c4

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 4321
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 4324
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x1ef73c28

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 4325
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 4286
    sget p1, Lcom/wukong/manager/b;->f:I

    add-int/2addr p0, p1

    .line 4287
    sget p1, Lcom/wukong/manager/b;->e:I

    xor-int v0, p0, p1

    and-int/lit8 v0, v0, 0x7

    if-eqz v0, :cond_29

    const/4 v1, 0x1

    if-eq v0, v1, :cond_21

    const/4 v1, 0x2

    if-eq v0, v1, :cond_1c

    const/4 v1, 0x3

    if-eq v0, v1, :cond_17

    ushr-int/2addr p1, v1

    :goto_15
    xor-int/2addr p0, p1

    goto :goto_2f

    :cond_17
    shl-int/lit8 p1, p0, 0x3

    sub-int p0, p1, p0

    goto :goto_2f

    .line 4290
    :cond_1c
    invoke-static {p0}, Ljava/lang/Integer;->reverse(I)I

    move-result p0

    goto :goto_2f

    .line 4289
    :cond_21
    sget-object p1, Lcom/wukong/manager/b;->g:[I

    array-length v0, p1

    sub-int/2addr v0, v1

    aget p1, p1, v0

    add-int/2addr p0, p1

    goto :goto_2f

    .line 4288
    :cond_29
    sget-object p1, Lcom/wukong/manager/b;->g:[I

    const/4 v0, 0x0

    aget p1, p1, v0

    goto :goto_15

    :goto_2f
    const p1, 0x6d2b79f5

    add-int/2addr p1, p0

    .line 4294
    sput p1, Lcom/wukong/manager/b;->f:I

    .line 4295
    sget p1, Lcom/wukong/manager/b;->e:I

    xor-int/2addr p0, p1

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 4298
    sget v0, Lcom/wukong/manager/b;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/b;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 4299
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 4300
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ch;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 4301
    sget-object p1, Lcom/wukong/manager/b;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x56

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

    .line 4305
    :cond_3
    sget v0, Lcom/wukong/manager/b;->e:I

    sget v1, Lcom/wukong/manager/b;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/g;->f(ILjava/lang/Object;)I

    move-result v0

    .line 4306
    invoke-static {v0, p1}, Lcom/wukong/manager/s;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 4307
    sget v1, Lcom/wukong/manager/b;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/b;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x56

    .line 4311
    invoke-static {p0, p1}, Lcom/wukong/manager/b;->f(ILjava/lang/Object;)I

    move-result p0

    .line 4312
    invoke-static {p0, p1}, Lcom/wukong/manager/ch;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 4313
    sget v0, Lcom/wukong/manager/b;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/g;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 4314
    :cond_17
    sget p1, Lcom/wukong/manager/b;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/s;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
