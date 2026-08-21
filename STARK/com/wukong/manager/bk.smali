.class final Lcom/wukong/manager/bk;
.super Ljava/lang/Object;
.source "SourceFile"


# static fields
.field private static e:I = 0x5c1a4f

.field private static f:I = 0x4c2c6df7

.field private static final g:[I


# direct methods
.method static constructor <clinit>()V
    .registers 5

    const v0, 0x4f7ba999

    const v1, 0x1cece9a6

    const v2, 0x261d4141

    const v3, 0x662579f1

    const v4, 0x2bb6411b

    .line 1189
    filled-new-array {v2, v3, v4, v0, v1}, [I

    move-result-object v0

    sput-object v0, Lcom/wukong/manager/bk;->g:[I

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

    const v1, 0x4b95063d  # 1.9532922E7f

    xor-int/2addr v1, p0

    .line 1226
    sget-object v2, Lcom/wukong/manager/bk;->g:[I

    array-length v3, v2

    rem-int/2addr v0, v3

    aget v0, v2, v0

    add-int/2addr v1, v0

    const v0, 0x63b76d61

    add-int/2addr v1, v0

    and-int/lit8 p0, p0, 0xf

    add-int/lit8 p0, p0, 0x1

    .line 1227
    invoke-static {v1, p0}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 v0, p0, 0xb

    xor-int/2addr p0, v0

    and-int/2addr p1, p0

    .line 1230
    array-length v0, v2

    rem-int/2addr p1, v0

    aget p1, v2, p1

    const v0, 0x4828e8c1

    xor-int/2addr p1, v0

    add-int/2addr p0, p1

    ushr-int/lit8 p1, p0, 0x3

    and-int/lit8 p1, p1, 0x7

    add-int/lit8 p1, p1, 0x3

    .line 1231
    invoke-static {p0, p1}, Ljava/lang/Integer;->rotateLeft(II)I

    move-result p0

    ushr-int/lit8 p1, p0, 0x10

    xor-int/2addr p0, p1

    return p0
.end method

.method public static f(ILjava/lang/Object;)I
    .registers 4

    .line 1192
    sget p1, Lcom/wukong/manager/bk;->f:I

    add-int/2addr p0, p1

    .line 1193
    sget p1, Lcom/wukong/manager/bk;->e:I

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

    .line 1196
    :cond_1c
    invoke-static {p0}, Ljava/lang/Integer;->reverse(I)I

    move-result p0

    goto :goto_2f

    .line 1195
    :cond_21
    sget-object p1, Lcom/wukong/manager/bk;->g:[I

    array-length v0, p1

    sub-int/2addr v0, v1

    aget p1, p1, v0

    add-int/2addr p0, p1

    goto :goto_2f

    .line 1194
    :cond_29
    sget-object p1, Lcom/wukong/manager/bk;->g:[I

    const/4 v0, 0x0

    aget p1, p1, v0

    goto :goto_15

    :goto_2f
    const p1, 0x6d2b79f5

    add-int/2addr p1, p0

    .line 1200
    sput p1, Lcom/wukong/manager/bk;->f:I

    .line 1201
    sget p1, Lcom/wukong/manager/bk;->e:I

    xor-int/2addr p0, p1

    return p0
.end method

.method public static g(Ljava/lang/String;I)Z
    .registers 3

    .line 1204
    sget v0, Lcom/wukong/manager/bk;->e:I

    xor-int/2addr p1, v0

    sget v0, Lcom/wukong/manager/bk;->f:I

    xor-int/2addr p1, v0

    if-eqz p0, :cond_d

    .line 1205
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    xor-int/2addr p1, v0

    .line 1206
    :cond_d
    invoke-static {p1, p0}, Lcom/wukong/manager/bv;->f(ILjava/lang/Object;)I

    move-result p0

    xor-int/2addr p0, p1

    and-int/lit8 p0, p0, 0x3

    .line 1207
    sget-object p1, Lcom/wukong/manager/bk;->g:[I

    array-length p1, p1

    add-int/lit8 p1, p1, 0x15

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

    .line 1211
    :cond_3
    sget v0, Lcom/wukong/manager/bk;->e:I

    sget v1, Lcom/wukong/manager/bk;->f:I

    xor-int/2addr v0, v1

    invoke-static {v0, p0}, Lcom/wukong/manager/e;->f(ILjava/lang/Object;)I

    move-result v0

    .line 1212
    invoke-static {v0, p1}, Lcom/wukong/manager/bm;->f(ILjava/lang/Object;)I

    move-result v1

    xor-int/2addr v0, v1

    .line 1213
    sget v1, Lcom/wukong/manager/bk;->e:I

    xor-int/2addr v1, v0

    sput v1, Lcom/wukong/manager/bk;->e:I

    and-int/lit8 v0, v0, 0x1

    if-nez v0, :cond_1b

    :goto_1a
    return-object p0

    :cond_1b
    return-object p1
.end method

.method public static i(ILjava/lang/Object;)I
    .registers 3

    add-int/lit8 p0, p0, 0x15

    .line 1217
    invoke-static {p0, p1}, Lcom/wukong/manager/bk;->f(ILjava/lang/Object;)I

    move-result p0

    .line 1218
    invoke-static {p0, p1}, Lcom/wukong/manager/bv;->f(ILjava/lang/Object;)I

    move-result v0

    xor-int/2addr p0, v0

    and-int/lit8 v0, p0, 0x1

    if-eqz v0, :cond_17

    .line 1219
    sget v0, Lcom/wukong/manager/bk;->e:I

    xor-int/2addr v0, p0

    invoke-static {v0, p1}, Lcom/wukong/manager/e;->f(ILjava/lang/Object;)I

    move-result p1

    xor-int/2addr p0, p1

    .line 1220
    :cond_17
    sget p1, Lcom/wukong/manager/bk;->f:I

    xor-int/2addr p1, p0

    const/4 v0, 0x0

    invoke-static {p1, v0}, Lcom/wukong/manager/bm;->f(ILjava/lang/Object;)I

    move-result p1

    add-int/2addr p0, p1

    return p0
.end method
