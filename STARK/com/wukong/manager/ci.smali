.class final Lcom/wukong/manager/ci;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x2d99a841

.field private static f:I = 0x592ebf87

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x7

    .line 2953
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/ci;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x7e29edd7
        0x203b7add
        0x1d20fd6e
        0x6b366a92
        0x4fb42444
        0x437489f0
        0x61b07219
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

    const v1, 0x58cf208a

    xor-int/2addr v1, p0

    .line 2985
    sget-object v2, Lcom/wukong/manager/ci;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x32d88454

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 2986
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 2989
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x6f295126

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 2990
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 3

    .line 2957
    :try_start_0
    sget v0, Lcom/wukong/manager/ci;->e:I

    or-int/lit8 v0, v0, 0x1

    and-int/lit16 v0, v0, 0xff

    div-int v0, p0, v0

    sget p0, Lcom/wukong/manager/ci;->f:I
    :try_end_a
    .catch Ljava/lang/ArithmeticException; {:try_start_0 .. :try_end_a} :catch_c

    xor-int/2addr p0, v0

    goto :goto_f

    :catch_c
    sget v0, Lcom/wukong/manager/ci;->e:I

    xor-int/2addr p0, v0

    :goto_f
    if-eqz p1, :cond_1e

    .line 2958
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    add-int/2addr p0, p1

    .line 2959
    :cond_1e
    sget p1, Lcom/wukong/manager/ci;->f:I

    xor-int/2addr p1, p0

    sput p1, Lcom/wukong/manager/ci;->f:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 2963
    sget v0, Lcom/wukong/manager/ci;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/ci;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 2964
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 2965
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/z;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 2966
    sget-object p1, Lcom/wukong/manager/ci;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x3a

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

    .line 2970
    :cond_3
    sget v0, Lcom/wukong/manager/ci;->e:I

    sget v1, Lcom/wukong/manager/ci;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/bz;->f(ILjava/lang/Object;)I

    move-result v0

    .line 2971
    invoke-static {v0, p1}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 2972
    sget v1, Lcom/wukong/manager/ci;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/ci;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x3a

    .line 2976
    invoke-static {p0, p1}, Lcom/wukong/manager/ci;->f(ILjava/lang/Object;)I

    move-result p0

    .line 2977
    invoke-static {p0, p1}, Lcom/wukong/manager/z;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 2978
    sget v0, Lcom/wukong/manager/ci;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/bz;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 2979
    :cond_17
    sget p1, Lcom/wukong/manager/ci;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bb;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
