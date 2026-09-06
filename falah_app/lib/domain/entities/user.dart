/// المستخدمُ كما يعرفه التطبيق — ما يردّه `/app/me` لا أكثر.
///
/// **`role` قراءةٌ فقط، ولا تُبنى عليها حمايةٌ في العميل.** الخادمُ يقرؤه
/// من القاعدة ولا يقبله من طلبٍ ولا كعكةٍ ولا ترويسة. وإخفاءُ زرٍّ هنا
/// راحةُ استعمالٍ لا حدُّ أمان: القرارُ في `falah/authz.py` وحده.
library;

class User {
  const User({
    required this.id,
    required this.email,
    required this.name,
    required this.watermark,
    required this.createdAt,
    required this.role,
  });

  final int id;
  final String email;
  final String name;

  /// علامةُ المستخدم على البطاقة — تُطبع في خانة الذيل اليمنى.
  final String watermark;
  final DateTime createdAt;

  /// `anonymous` · `user` · `moderator` · `admin` · `super_admin`
  final String role;

  User copyWith({String? name, String? watermark}) => User(
        id: id,
        email: email,
        name: name ?? this.name,
        watermark: watermark ?? this.watermark,
        createdAt: createdAt,
        role: role,
      );

  @override
  bool operator ==(Object other) =>
      other is User &&
      other.id == id &&
      other.email == email &&
      other.name == name &&
      other.watermark == watermark &&
      other.role == role;

  @override
  int get hashCode => Object.hash(id, email, name, watermark, role);
}
