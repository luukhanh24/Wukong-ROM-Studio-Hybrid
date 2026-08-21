.class final Lcom/wukong/manager/cm;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0xdc5746f

.field private static f:I = 0x635a9f60

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 5

    const v0, 0x69f04b98

    const v1, 0x156da553

    const v2, 0x30a6ce41

    const v3, 0x32582a35

    const v4, 0x542f1278

    .line 237
    filled-new-array {v2, v3, v4, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/cm;->g:[I

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

    const v1, 0x89ff086

    xor-int/2addr v1, p0

    .line 274
    sget-object v2, Lcom/wukong/manager/cm;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x6ec65392

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 275
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 278
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x2a001a06

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 279
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 240
    sget p1, Lcom/wukong/manager/cm;->f:I

    add-int/2addr p0, p1

    .line 241
    sget p1, Lcom/wukong/manager/cm;->e:I

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

    .line 244
    :cond_1c
    invoke-static {p0}, Ljava/lang/Integer;->reverse(I)I

    move-result p0

    goto :goto_2f

    .line 243
    :cond_21
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    array-length v0, p1

    sub-int/2addr v0, v1

    aget p1, p1, v0

    add-int/2addr p0, p1

    goto :goto_2f

    .line 242
    :cond_29
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    const/4 v0, 0x0

    aget p1, p1, v0

    goto :goto_15

    :goto_2f
    const p1, 0x6d2b79f5

    add-int/2addr p1, p0

    .line 248
    sput p1, Lcom/wukong/manager/cm;->f:I

    .line 249
    sget p1, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr p0, p1

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 252
    sget v0, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 253
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 254
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/at;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 255
    sget-object p1, Lcom/wukong/manager/cm;->g:[I

    array-length p1, p1

    const/4 v0, 0x1

    add-int/2addr p1, v0

    and-int/lit8 p1, p1, 0x3

    if-ne p0, p1, :cond_1e

    return v0

    :cond_1e
    const/4 p0, 0x0

    return p0
.end method

.method public static h(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .registers 4

    if-ne p0, p1, :cond_3

    goto :goto_1a

    .line 259
    :cond_3
    sget v0, Lcom/wukong/manager/cm;->e:I

    sget v1, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/af;->f(ILjava/lang/Object;)I

    move-result v0

    .line 260
    invoke-static {v0, p1}, Lcom/wukong/manager/cb;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 261
    sget v1, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/cm;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x1

    .line 265
    invoke-static {p0, p1}, Lcom/wukong/manager/cm;->f(ILjava/lang/Object;)I

    move-result p0

    .line 266
    invoke-static {p0, p1}, Lcom/wukong/manager/at;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 267
    sget v0, Lcom/wukong/manager/cm;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/af;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 268
    :cond_17
    sget p1, Lcom/wukong/manager/cm;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/cb;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
