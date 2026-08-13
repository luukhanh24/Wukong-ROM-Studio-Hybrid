.class final Lcom/wukong/manager/u;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x3a90eb70

.field private static f:I = 0x1d89a93f

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 1049
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/u;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x12530081
        0x4ca3d3f5  # 8.589303E7f
        0x55ec5bf4
        0x1386cff1
        0x7ac96091
        0x3da6a83b
        0x65b97854
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

    const v1, 0x1815d44e

    xor-int/2addr v1, p0

    .line 1081
    sget-object v2, Lcom/wukong/manager/u;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x5036f9e0

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1082
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1085
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x43735540

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1086
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 1053
    :try_start_0
    sget v0, Lcom/wukong/manager/u;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/u;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/u;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 1054
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 1055
    :cond_1e
    sget p1, Lcom/wukong/manager/u;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/u;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1059
    sget v0, Lcom/wukong/manager/u;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/u;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1060
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1061
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/l;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1062
    sget-object p1, Lcom/wukong/manager/u;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x12

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

    .line 1066
    :cond_3
    sget v0, Lcom/wukong/manager/u;->e:I

    sget v1, Lcom/wukong/manager/u;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/an;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1067
    invoke-static {v0, p1}, Lcom/wukong/manager/bp;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1068
    sget v1, Lcom/wukong/manager/u;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/u;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x12

    .line 1072
    invoke-static {p0, p1}, Lcom/wukong/manager/u;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1073
    invoke-static {p0, p1}, Lcom/wukong/manager/l;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1074
    sget v0, Lcom/wukong/manager/u;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/an;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1075
    :cond_17
    sget p1, Lcom/wukong/manager/u;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bp;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
