.class final Lcom/wukong/manager/u;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x3173fa43

.field private static f:I = 0x40e9f30c

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 1

    const/4 v0, 0x6

    .line 4095
    new-array v0, v0, [I

    fill-array-data v0, :array_a

    sput-object v0, Lcom/wukong/manager/u;->g:[I

    return-void

    nop

    :array_a
    .array-data 4
        0x4bf092c0  # 3.1532416E7f
        0x7d40ce8d
        0xf3b8396
        0x7bd3ebce
        0x557dfec2
        0x6faeca8c
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

    const v1, 0x1b7a88c3

    xor-int/2addr v1, p0

    .line 4130
    sget-object v2, Lcom/wukong/manager/u;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x36b0760a

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 4131
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 4134
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x62b07594

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 4135
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 4098
    sget p1, Lcom/wukong/manager/u;->e:I

    sget v0, Lcom/wukong/manager/u;->f:I

    add-int/2addr p1, v0

    xor-int/2addr p0, p1

    const/4 p1, 0x0

    :goto_7
    const/4 v0, 0x4

    if-ge p1, v0, :cond_1e

    .line 4101
    sget-object v0, Lcom/wukong/manager/u;->g:[I

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

    .line 4104
    sput p0, Lcom/wukong/manager/u;->e:I

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 4108
    sget v0, Lcom/wukong/manager/u;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/u;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 4109
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 4110
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/ba;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 4111
    sget-object p1, Lcom/wukong/manager/u;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x52

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

    .line 4115
    :cond_3
    sget v0, Lcom/wukong/manager/u;->e:I

    sget v1, Lcom/wukong/manager/u;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/cn;->f(ILjava/lang/Object;)I

    move-result v0

    .line 4116
    invoke-static {v0, p1}, Lcom/wukong/manager/ca;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 4117
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

    add-int/lit8 p0, p0, 0x52

    .line 4121
    invoke-static {p0, p1}, Lcom/wukong/manager/u;->f(ILjava/lang/Object;)I

    move-result p0

    .line 4122
    invoke-static {p0, p1}, Lcom/wukong/manager/ba;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 4123
    sget v0, Lcom/wukong/manager/u;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/cn;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 4124
    :cond_17
    sget p1, Lcom/wukong/manager/u;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/ca;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
