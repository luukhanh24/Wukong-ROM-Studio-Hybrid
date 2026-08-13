.class final Lcom/wukong/manager/as;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x11fb9389

.field private static f:I = 0xeca15b4

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 3191
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/as;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x4da90bb4  # 3.5451456E8f
        0x628f6802
        0x60016202
        0x480f365b
        0x20c35a27
        0x61b925b5
        0x331bd4e8
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

    const v1, 0x2c1592e9

    xor-int/2addr v1, p0

    .line 3223
    sget-object v2, Lcom/wukong/manager/as;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x61a1a49d

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 3224
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 3227
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x6a4a2dcb

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 3228
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 3195
    :try_start_0
    sget v0, Lcom/wukong/manager/as;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/as;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/as;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 3196
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 3197
    :cond_1e
    sget p1, Lcom/wukong/manager/as;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/as;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 3201
    sget v0, Lcom/wukong/manager/as;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/as;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 3202
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 3203
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/aj;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 3204
    sget-object p1, Lcom/wukong/manager/as;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x3f

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

    .line 3208
    :cond_3
    sget v0, Lcom/wukong/manager/as;->e:I

    sget v1, Lcom/wukong/manager/as;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bt;->f(ILjava/lang/Object;)I

    move-result v0

    .line 3209
    invoke-static {v0, p1}, Lcom/wukong/manager/cg;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 3210
    sget v1, Lcom/wukong/manager/as;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/as;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x3f

    .line 3214
    invoke-static {p0, p1}, Lcom/wukong/manager/as;->f(ILjava/lang/Object;)I

    move-result p0

    .line 3215
    invoke-static {p0, p1}, Lcom/wukong/manager/aj;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 3216
    sget v0, Lcom/wukong/manager/as;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bt;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 3217
    :cond_17
    sget p1, Lcom/wukong/manager/as;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/cg;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
